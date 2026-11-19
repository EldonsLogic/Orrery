import type { ChatEvent, ChatPort, ConfirmDecision, SendRequest } from './types';

export type Script = (req: SendRequest) => ReadonlyArray<ChatEvent>;
export type FakePort = ChatPort & {
  /** Everything the screen asked for, for assertions. */
  readonly sent: SendRequest[];
  readonly decisions: ConfirmDecision[];
  cancelled: number;
  /** Deliver the next held event (manual mode); returns false when none is left. */
  step(): boolean;
  /** Deliver an event now. */
  emit(e: ChatEvent): void;
};

/**
 * Scripted ChatPort for tests and the fixture-driven page. `manual` holds events until `step()` so a
 * test can look at the screen mid-run; otherwise they arrive at once, or one per `delayMs` when given.
 */
export function createFakePort(script: Script, opts: { manual?: boolean; delayMs?: number } = {}): FakePort {
  const listeners = new Set<(e: ChatEvent) => void>();
  let queue: ChatEvent[] = [];
  let timer: ReturnType<typeof setTimeout> | undefined;
  const emit = (e: ChatEvent) => [...listeners].forEach((l) => l(e));
  const pump = () => {
    if (opts.manual) return;
    if (!opts.delayMs) {
      while (queue.length) emit(queue.shift() as ChatEvent);
      return;
    }
    if (timer || !queue.length) return;
    timer = setTimeout(() => {
      timer = undefined;
      const e = queue.shift();
      if (e) emit(e);
      pump();
    }, opts.delayMs);
  };
  const port: FakePort = {
    sent: [],
    decisions: [],
    cancelled: 0,
    send(req) {
      port.sent.push(req);
      queue = [{ type: 'run_started', runId: `run-${port.sent.length}` }, ...script(req)];
      pump();
    },
    cancel() {
      port.cancelled += 1;
      queue = [];
      if (timer) clearTimeout(timer);
      timer = undefined;
      emit({ type: 'run_finished', outcome: 'cancelled' });
    },
    respond(d) {
      port.decisions.push(d);
      queue = d.accepted
        ? [
            { type: 'run_started', runId: `run-confirm-${port.decisions.length}` },
            { type: 'text_delta', messageId: `m-confirm-${port.decisions.length}`, delta: 'Done.' },
            { type: 'text_end', messageId: `m-confirm-${port.decisions.length}` },
            { type: 'run_finished', outcome: 'done' },
          ]
        : [{ type: 'run_finished', outcome: 'cancelled' }];
      pump();
    },
    subscribe(l) {
      listeners.add(l);
      return () => void listeners.delete(l);
    },
    step() {
      const e = queue.shift();
      if (!e) return false;
      emit(e);
      return true;
    },
    emit,
  };
  return port;
}
