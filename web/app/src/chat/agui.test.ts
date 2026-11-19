// WEB-026: AG-UI stream client. Parser, allow-list mapper, port (abort, timeout, retry) and hostile input.
import { describe, expect, it, vi } from 'vitest';
import { AguiMapper } from './aguiEvents';
import { createAguiPort } from './aguiPort';
import { chatReducer, initialChatState } from './reducer';
import { SseError, SseParser, MAX_SSE_DATA } from './sse';
import type { ChatEvent, ChatState } from './types';

const frame = (o: unknown) => `data: ${JSON.stringify(o)}\n\n`;
const RUN = 'run-1';
const started = { type: 'RUN_STARTED', threadId: 't1', runId: RUN };
const finished = { type: 'RUN_FINISHED', threadId: 't1', runId: RUN, outcome: { type: 'success' } };

describe('SseParser', () => {
  it('parses frames split at any byte, CRLF and CR, multi-line data and ignores other fields', () => {
    const wire = ': hi\r\nevent: x\r\nid: 9\r\ndata: a\r\ndata: b\r\n\r\ndata: c\r\r';
    for (let cut = 0; cut <= wire.length; cut++) {
      const p = new SseParser();
      expect([...p.push(wire.slice(0, cut)), ...p.push(wire.slice(cut)), ...p.end()]).toEqual(['a\nb', 'c']);
    }
  });
  it('emits nothing for an empty or comment-only event and fails on oversized input', () => {
    expect(new SseParser().push(': ping\n\n\n\n')).toEqual([]);
    expect(() => new SseParser().push('data: ' + 'x'.repeat(MAX_SSE_DATA + 1) + '\n')).toThrow(SseError);
    expect(() => new SseParser().push('x'.repeat(600 * 1024))).toThrow(SseError);
  });
});

describe('AguiMapper', () => {
  const run = (events: unknown[]) => {
    const m = new AguiMapper(RUN);
    return events.flatMap((e) => m.map(e).events);
  };
  it('maps a normal run to screen events', () => {
    expect(
      run([
        started,
        { type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'sales_order.list' },
        { type: 'TOOL_CALL_ARGS', toolCallId: 'c1', delta: '{"x":1}' },
        { type: 'TOOL_CALL_END', toolCallId: 'c1' },
        { type: 'TOOL_CALL_RESULT', toolCallId: 'c1', messageId: 'r1', content: '{"status":"ok"}' },
        { type: 'TEXT_MESSAGE_START', messageId: 'm1', role: 'assistant' },
        { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'مرحبا hello' },
        { type: 'TEXT_MESSAGE_END', messageId: 'm1' },
        finished,
      ]),
    ).toEqual<ChatEvent[]>([
      { type: 'run_started', runId: RUN },
      { type: 'tool_call', callId: 'c1', tool: 'sales_order.list', risk: 'R4' },
      { type: 'tool_result', callId: 'c1', outcome: 'ok' },
      { type: 'text_delta', messageId: 'm1', delta: 'مرحبا hello' },
      { type: 'text_end', messageId: 'm1' },
      { type: 'run_finished', outcome: 'done' },
    ]);
  });
  it('an interrupt only ends the run; its status and payload decide nothing', () => {
    const out = run([
      started,
      { type: 'CUSTOM', name: 'approval.pending', value: { approvalId: 'ap_1', tool: 'sales_invoice.create' } },
      { ...finished, outcome: { type: 'interrupt', interrupts: [{ id: 'ap_1', status: 'approved', payload: { approved: true } }] } },
    ]);
    expect(out.map((e) => e.type)).toEqual(['run_started', 'approval_pending', 'run_finished']);
    expect(JSON.stringify(out)).not.toContain('approved');
    expect(out[2]).toEqual({ type: 'run_finished', outcome: 'interrupt' });
  });
  it('drops Raw, Reasoning, state, unknown types and unknown Custom names', () => {
    const out = run([
      started,
      { type: 'RAW', event: {} },
      { type: 'REASONING_MESSAGE_CONTENT', delta: 'secret' },
      { type: 'STATE_SNAPSHOT', snapshot: { a: 1 } },
      { type: 'STATE_DELTA', delta: [] },
      { type: 'CUSTOM', name: 'ui.render', value: { html: '<script>' } },
      { type: 'CUSTOM', name: 'tool.progress', value: {} },
      { type: 'MADE_UP' },
      {},
      null,
      [],
      'str',
      7,
    ]);
    expect(out).toEqual([{ type: 'run_started', runId: RUN }]);
  });
  it('fails closed when the stream does not open our own run', () => {
    expect(new AguiMapper(RUN).map({ type: 'TEXT_MESSAGE_START', messageId: 'm' })).toMatchObject({ terminal: true, fault: 'bad_run' });
    expect(new AguiMapper(RUN).map({ ...started, runId: 'other' })).toMatchObject({ terminal: true, fault: 'bad_run' });
  });
  it('rejects malformed ids, tool names, roles and out-of-order events', () => {
    const out = run([
      started,
      { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'no start' },
      { type: 'TEXT_MESSAGE_START', messageId: 'bad id<', role: 'assistant' },
      { type: 'TEXT_MESSAGE_START', messageId: 'u1', role: 'user' },
      { type: 'TEXT_MESSAGE_CONTENT', messageId: 'u1', delta: 'x' },
      { type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'sales.list' + '<img onerror=1>' },
      { type: 'TOOL_CALL_START', toolCallId: 'c2', toolCallName: 'NoDot' },
      { type: 'TOOL_CALL_RESULT', toolCallId: 'never', messageId: 'r', content: '{"status":"ok"}' },
      { type: 'TEXT_MESSAGE_START', messageId: 'm2' },
      { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm2', delta: 5 },
      { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm2', delta: '' },
      { type: 'TEXT_MESSAGE_END', messageId: 'm9' },
      { type: 'CUSTOM', name: 'approval.pending', value: { approvalId: 'a', tool: '<b>x</b>' } },
      { type: 'CUSTOM', name: 'approval.pending', value: null },
    ]);
    expect(out).toEqual([{ type: 'run_started', runId: RUN }]);
  });
  it('treats unparseable or unknown tool results as errors, never success; prototype keys too', () => {
    const results = ['not json', '{"status":"__proto__"}', '{"status":"constructor"}', '{"status":5}', '[]', 'null'].map((content, i) => {
      const m = new AguiMapper(RUN);
      m.map(started);
      m.map({ type: 'TOOL_CALL_START', toolCallId: 'c', toolCallName: 'a.b' });
      return m.map({ type: 'TOOL_CALL_RESULT', toolCallId: 'c', messageId: 'r' + i, content }).events[0];
    });
    for (const r of results) expect(r).toEqual({ type: 'tool_result', callId: 'c', outcome: 'error' });
  });
  it('shows a RUN_ERROR through our code only, never its message', () => {
    const e = run([started, { type: 'RUN_ERROR', message: 'Traceback in module', code: 'rate_limited' }]);
    expect(e[1]).toEqual({ type: 'run_error', code: 'rate_limited' });
    expect(JSON.stringify(e)).not.toMatch(/Traceback/);
    expect(run([started, { type: 'RUN_ERROR', message: 'x', code: '<script>' }])[1]).toEqual({ type: 'run_error', code: 'unknown' });
  });
  it('ignores events after the terminal one and caps text per run', () => {
    expect(run([started, finished, { type: 'TEXT_MESSAGE_START', messageId: 'm' }, finished])).toHaveLength(2);
    const m = new AguiMapper(RUN);
    m.map(started);
    m.map({ type: 'TEXT_MESSAGE_START', messageId: 'm' });
    const big = { type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'x'.repeat(150_000) };
    expect(m.map(big).events).toHaveLength(1);
    expect(m.map(big).events).toHaveLength(0);
  });
  it('model text with markup or bidi controls reaches the screen only as plain text', () => {
    const s = [
      { type: 'run_started', runId: RUN },
      { type: 'text_delta', messageId: 'm', delta: '<img src=x onerror=alert(1)>‮evil' },
    ] as ChatEvent[];
    const state = s.reduce<ChatState>((a, event) => chatReducer(a, { kind: 'event', event }), { ...initialChatState(), run: 'running' } as ChatState);
    expect(state.messages[0].text).toBe('<img src=x onerror=alert(1)>evil'); // rendered by React as text; bidi control removed
  });
});

// ---- port ----
const sseResponse = (chunks: string[], init: ResponseInit = {}) => {
  const enc = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(c) {
        chunks.forEach((x) => c.enqueue(enc.encode(x)));
        c.close();
      },
    }),
    { status: 200, headers: { 'content-type': 'text/event-stream' }, ...init },
  );
};
const setup = (fetchImpl: (url: string, init: RequestInit) => Promise<Response>, extra = {}) => {
  let n = 0;
  const f = vi.fn(fetchImpl);
  const port = createAguiPort({
    url: 'https://gw.test/v1/agent/stream',
    getToken: () => 'tok',
    locale: () => 'ar',
    fetch: f as unknown as typeof fetch,
    newId: () => (n++ === 0 ? 't1' : n === 2 ? RUN : `id${n}`),
    sleep: async () => {},
    ...extra,
  });
  const got: ChatEvent[] = [];
  port.subscribe((e) => got.push(e));
  const settled = () => vi.waitFor(() => expect(got.some((e) => e.type === 'run_finished' || e.type === 'run_error')).toBe(true));
  return { port, f, got, settled };
};

describe('createAguiPort', () => {
  it('posts a minimal untrusted-safe body with the token and language, and streams events', async () => {
    const wire = [frame(started), frame({ type: 'TEXT_MESSAGE_START', messageId: 'm1' }), frame({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: 'hi' })];
    const { port, f, got, settled } = setup(async () => sseResponse([wire[0], wire[1].slice(0, 9), wire[1].slice(9) + wire[2], frame(finished)]));
    port.send({ text: 'hello', mode: 'ask' });
    await settled();
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('https://gw.test/v1/agent/stream');
    const h = init.headers as Record<string, string>;
    expect(h.authorization).toBe('Bearer tok');
    expect(h['accept-language']).toBe('ar');
    expect(init.credentials).toBe('omit');
    const body = JSON.parse(init.body as string);
    expect(body).toMatchObject({ threadId: 't1', runId: RUN, tools: [], context: [], state: {}, messages: [{ role: 'user', content: 'hello' }] });
    expect(Object.keys(body).sort()).toEqual(['context', 'forwardedProps', 'messages', 'runId', 'state', 'threadId', 'tools']);
    expect(got.map((e) => e.type)).toEqual(['run_started', 'text_delta', 'run_finished']);
  });
  it('skips malformed frames and keeps going', async () => {
    const { port, got, settled } = setup(async () => sseResponse([frame(started), 'data: {not json\n\n', 'data: \n\n', frame(finished)]));
    port.send({ text: 'x', mode: 'ask' });
    await settled();
    expect(got.map((e) => e.type)).toEqual(['run_started', 'run_finished']);
  });
  it('a stream that ends without a terminal event is an error, not a success', async () => {
    const { port, got, settled } = setup(async () => sseResponse([frame(started)]));
    port.send({ text: 'x', mode: 'ask' });
    await settled();
    expect(got.at(-1)).toEqual({ type: 'run_error', code: 'unavailable' });
  });
  it('a stream for another run is refused', async () => {
    const { port, got, settled } = setup(async () => sseResponse([frame({ ...started, runId: 'evil' }), frame(finished)]));
    port.send({ text: 'x', mode: 'ask' });
    await settled();
    expect(got).toEqual([{ type: 'run_error', code: 'unavailable' }]);
  });
  it.each([
    [401, 'forbidden'],
    [403, 'forbidden'],
    [413, 'invalid_request'],
    [500, 'unavailable'],
    [418, 'unavailable'],
  ])('maps HTTP %i to the code %s without replaying', async (status, code) => {
    const { port, got, settled, f } = setup(async () => new Response('stack trace', { status }));
    port.send({ text: 'x', mode: 'ask' });
    await settled();
    expect(got).toEqual([{ type: 'run_error', code }]);
    expect(f).toHaveBeenCalledTimes(1);
  });
  it('retries a refused connect (503) a bounded number of times, then succeeds or gives up', async () => {
    let n = 0;
    const ok = setup(async () => (n++ < 2 ? new Response('', { status: 503 }) : sseResponse([frame(started), frame(finished)])));
    ok.port.send({ text: 'x', mode: 'ask' });
    await ok.settled();
    expect(ok.f).toHaveBeenCalledTimes(3);
    expect(ok.got.at(-1)).toEqual({ type: 'run_finished', outcome: 'done' });
    const bad = setup(async () => new Response('', { status: 429 }));
    bad.port.send({ text: 'x', mode: 'ask' });
    await bad.settled();
    expect(bad.f).toHaveBeenCalledTimes(3);
    expect(bad.got).toEqual([{ type: 'run_error', code: 'rate_limited' }]);
  });
  it('does not replay after a network failure or a mid-stream drop', async () => {
    const net = setup(async () => {
      throw new TypeError('network');
    });
    net.port.send({ text: 'x', mode: 'ask' });
    await net.settled();
    expect(net.f).toHaveBeenCalledTimes(1);
    expect(net.got).toEqual([{ type: 'run_error', code: 'unavailable' }]);
    const drop = setup(async () => {
      const enc = new TextEncoder();
      return new Response(new ReadableStream({ start(c) { c.enqueue(enc.encode(frame(started))); c.error(new Error('reset')); } }), { headers: { 'content-type': 'text/event-stream' } });
    });
    drop.port.send({ text: 'x', mode: 'ask' });
    await drop.settled();
    expect(drop.f).toHaveBeenCalledTimes(1);
    expect(drop.got.at(-1)).toEqual({ type: 'run_error', code: 'unavailable' });
  });
  it('refuses a response that is not an event stream', async () => {
    const { port, got, settled } = setup(async () => new Response('<html>', { status: 200, headers: { 'content-type': 'text/html' } }));
    port.send({ text: 'x', mode: 'ask' });
    await settled();
    expect(got).toEqual([{ type: 'run_error', code: 'unavailable' }]);
  });
  it('cancel aborts the request, reports cancelled once and ignores later events', async () => {
    let signal: AbortSignal | undefined;
    const { port, got, f } = setup((_u, init) => {
      signal = init.signal as AbortSignal;
      return new Promise<Response>((_r, rej) => signal!.addEventListener('abort', () => rej(new DOMException('a', 'AbortError'))));
    });
    port.send({ text: 'x', mode: 'ask' });
    await vi.waitFor(() => expect(f).toHaveBeenCalled());
    port.cancel();
    await Promise.resolve();
    expect(signal!.aborted).toBe(true);
    expect(got).toEqual([{ type: 'run_finished', outcome: 'cancelled' }]);
    port.send({ text: 'again', mode: 'ask' }); // a new run may start straight away
    await vi.waitFor(() => expect(f).toHaveBeenCalledTimes(2));
  });
  it('ends a silent stream with a timeout', async () => {
    const { port, got, settled } = setup((_u, init) => new Promise<Response>((_r, rej) => (init.signal as AbortSignal).addEventListener('abort', () => rej(new DOMException('a', 'AbortError')))), { idleTimeoutMs: 20 });
    port.send({ text: 'x', mode: 'ask' });
    await settled();
    expect(got).toEqual([{ type: 'run_error', code: 'timeout' }]);
  });
  it('respond sends nothing: confirmations and approvals never travel on the stream', () => {
    const { port, f, got } = setup(async () => sseResponse([]));
    port.respond({ confirmId: 'k1', accepted: true });
    expect(f).not.toHaveBeenCalled();
    expect(got).toEqual([{ type: 'run_error', code: 'unavailable' }]);
  });
  it('an oversized hostile event ends the run with an error', async () => {
    const { port, got, settled } = setup(async () => sseResponse([frame(started), 'data: ' + 'x'.repeat(MAX_SSE_DATA + 5) + '\n\n']));
    port.send({ text: 'x', mode: 'ask' });
    await settled();
    expect(got.at(-1)).toEqual({ type: 'run_error', code: 'invalid_request' });
  });
});
