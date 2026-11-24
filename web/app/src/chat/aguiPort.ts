import { AguiMapper } from './aguiEvents';
import { SseError, SseParser } from './sse';
import type { ChatEvent, ChatPort, ConfirmDecision, SendRequest } from './types';

/**
 * ChatPort over AG-UI (HTTP POST + SSE, ADR-0044 item 9). Transport only: the stream never decides anything.
 * - No client tools, no client state: the body carries ids, the user text and a mode hint the server ignores.
 * - Confirmation answers and approvals are never sent over this port; approvals are decided at the approval
 *   endpoint by an authenticated call (ADR-0044 item 2), so `respond` sends nothing.
 * - A broken stream is never replayed (a replay could repeat a write); only a refused connect (503, 429)
 *   is retried, a bounded number of times. After that the user can send again.
 */
export const AGENT_STREAM_PATH = '/v1/agent/stream';

export type AguiPortOptions = {
  /** Gateway origin plus path, e.g. `${base}${AGENT_STREAM_PATH}`. The tenant comes from the token, never from here. */
  url: string;
  getToken: () => string | Promise<string>;
  locale?: () => string;
  fetch?: typeof fetch;
  newId?: () => string;
  /** No bytes for this long ends the run with a timeout error. */
  idleTimeoutMs?: number;
  maxRetries?: number;
  sleep?: (ms: number) => Promise<void>;
};

const STATUS_CODE: Record<number, string> = { 400: 'invalid_request', 413: 'invalid_request', 401: 'forbidden', 403: 'forbidden', 429: 'rate_limited' };
const RETRYABLE = new Set([429, 503]);

const defaultId = (): string => `c${globalThis.crypto.randomUUID()}`;

export function createAguiPort(opts: AguiPortOptions): ChatPort {
  const doFetch = opts.fetch ?? ((...a: Parameters<typeof fetch>) => globalThis.fetch(...a));
  const newId = opts.newId ?? defaultId;
  const idleMs = opts.idleTimeoutMs ?? 60_000;
  const maxRetries = opts.maxRetries ?? 2;
  const sleep = opts.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)));
  const threadId = newId();
  const listeners = new Set<(e: ChatEvent) => void>();
  let current: { abort: AbortController; gen: number } | null = null;
  let gen = 0;

  const emit = (g: number, e: ChatEvent) => {
    if (!current || current.gen !== g) return; // a stale run never reaches the screen
    [...listeners].forEach((l) => l(e));
  };

  async function run(g: number, req: SendRequest, abort: AbortController): Promise<void> {
    const runId = newId();
    let terminal = false;
    const finish = (e: ChatEvent) => {
      if (terminal) return;
      terminal = true;
      emit(g, e);
    };
    let timedOut = false;
    let idle: ReturnType<typeof setTimeout> | undefined;
    const arm = () => {
      if (idle) clearTimeout(idle);
      idle = setTimeout(() => {
        timedOut = true;
        abort.abort();
      }, idleMs);
    };
    try {
      const body = JSON.stringify({
        threadId,
        runId,
        messages: [{ id: newId(), role: 'user', content: req.text }],
        tools: [],
        context: [],
        state: {},
        forwardedProps: { mode: req.mode }, // a hint; the server never trusts it
      });
      let res: Response | null = null;
      for (let attempt = 0; ; attempt++) {
        const token = await opts.getToken();
        arm();
        res = await doFetch(opts.url, {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            accept: 'text/event-stream',
            authorization: `Bearer ${token}`,
            'accept-language': opts.locale?.() ?? 'en',
          },
          body,
          signal: abort.signal,
          cache: 'no-store',
          credentials: 'omit',
          redirect: 'error',
        });
        if (!RETRYABLE.has(res.status) || attempt >= maxRetries) break;
        await res.body?.cancel().catch(() => undefined);
        await sleep(400 * 2 ** attempt);
        if (abort.signal.aborted) throw new DOMException('aborted', 'AbortError');
      }
      if (!res.ok) {
        await res.body?.cancel().catch(() => undefined);
        return finish({ type: 'run_error', code: STATUS_CODE[res.status] ?? 'unavailable' });
      }
      const type = res.headers.get('content-type') ?? '';
      if (!type.toLowerCase().startsWith('text/event-stream') || !res.body) {
        await res.body?.cancel().catch(() => undefined);
        return finish({ type: 'run_error', code: 'unavailable' });
      }
      const mapper = new AguiMapper(runId);
      const parser = new SseParser();
      const decoder = new TextDecoder('utf-8');
      const reader = res.body.getReader();
      try {
        while (!terminal) {
          arm();
          const { done, value } = await reader.read();
          const text = done ? decoder.decode() : decoder.decode(value, { stream: true });
          for (const data of done ? parser.push(text, true) : parser.push(text)) {
            let parsed: unknown;
            try {
              parsed = JSON.parse(data);
            } catch {
              continue; // malformed frame: dropped, the stream goes on
            }
            const m = mapper.map(parsed);
            m.events.forEach((e) => (e.type === 'run_finished' || e.type === 'run_error' ? finish(e) : emit(g, e)));
            if (m.fault) finish({ type: 'run_error', code: 'unavailable' });
            if (terminal) break;
          }
          if (done) break;
        }
      } finally {
        await reader.cancel().catch(() => undefined);
      }
      // The stream closed without RUN_FINISHED or RUN_ERROR: the run is unfinished, never shown as done.
      finish({ type: 'run_error', code: 'unavailable' });
    } catch (err) {
      if (abort.signal.aborted && !timedOut) return finish({ type: 'run_finished', outcome: 'cancelled' });
      if (timedOut) return finish({ type: 'run_error', code: 'timeout' });
      finish({ type: 'run_error', code: err instanceof SseError ? 'invalid_request' : 'unavailable' });
    } finally {
      if (idle) clearTimeout(idle);
      if (current?.gen === g) current = null;
    }
  }

  return {
    send(req: SendRequest) {
      if (current) return; // one run at a time
      const abort = new AbortController();
      gen += 1;
      current = { abort, gen };
      void run(gen, req, abort);
    },
    cancel() {
      if (!current) return;
      const { abort, gen: g } = current;
      emit(g, { type: 'run_finished', outcome: 'cancelled' });
      current = null; // later events of this run are ignored
      abort.abort();
    },
    /** Intentionally sends nothing: a confirmation or approval is never carried by the stream. */
    respond(_decision: ConfirmDecision) {
      void _decision;
      [...listeners].forEach((l) => l({ type: 'run_error', code: 'unavailable' }));
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
  };
}
