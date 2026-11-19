import type { ChatEvent, ToolOutcome } from './types';

/**
 * Maps AG-UI 1.0 wire events (SCREAMING_SNAKE type, camelCase fields, as emitted by services/operate/agui)
 * to the screen's ChatEvent allow-list (ADR-0044 items 1 to 3). Everything is untrusted: unknown types,
 * Raw and Reasoning events, unknown Custom names, malformed fields and out-of-order events yield nothing.
 * Nothing here reads an interrupt status or payload as a decision; an interrupt only closes the run.
 * Tool arguments, state snapshots and deltas are never rendered (no component exists for them yet).
 */
const ID = /^[A-Za-z0-9_\-:.]{1,128}$/;
const TOOL = /^[a-z][a-z0-9_]{0,47}(\.[a-z][a-z0-9_]{0,47}){1,3}$/;
const CODE = /^[a-z][a-z0-9_]{0,63}$/;
const isId = (v: unknown): v is string => typeof v === 'string' && ID.test(v);

export const MAX_TEXT_PER_RUN = 200_000;
export const MAX_MESSAGES = 200;
export const MAX_TOOL_CALLS = 100;

export type Mapped = { events: ChatEvent[]; terminal: boolean; fault?: 'bad_run' };

const RESULT: Record<string, ToolOutcome> = {
  ok: 'ok',
  success: 'ok',
  denied: 'denied',
  pending_approval: 'pending_approval',
  approval_required: 'pending_approval',
  error: 'error',
};

/** Per-run, stateful mapper. Create one for each run; discard it when the run ends. */
export class AguiMapper {
  private started = false;
  private ended = false;
  private text = 0;
  private readonly messages = new Map<string, boolean>(); // id -> open
  private readonly calls = new Map<string, { open: boolean; tool: string }>();
  private readonly approvals = new Set<string>();

  constructor(private readonly runId: string) {}

  get done(): boolean {
    return this.ended;
  }

  map(raw: unknown): Mapped {
    const none: Mapped = { events: [], terminal: false };
    if (this.ended || typeof raw !== 'object' || raw === null || Array.isArray(raw)) return none;
    const e = raw as Record<string, unknown>;
    if (!this.started) {
      // The first event must open our own run; anything else is a stream we do not trust.
      if (e.type === 'RUN_STARTED' && e.runId === this.runId) {
        this.started = true;
        return { events: [{ type: 'run_started', runId: this.runId }], terminal: false };
      }
      return { events: [], terminal: true, fault: 'bad_run' };
    }
    switch (e.type) {
      case 'RUN_STARTED':
        return none; // a second start is ignored
      case 'RUN_FINISHED': {
        if (e.runId !== this.runId) return none;
        this.ended = true;
        const o = e.outcome as { type?: unknown } | undefined;
        const interrupt = typeof o === 'object' && o !== null && o.type === 'interrupt';
        return { events: [{ type: 'run_finished', outcome: interrupt ? 'interrupt' : 'done' }], terminal: true };
      }
      case 'RUN_ERROR': {
        this.ended = true;
        // The message is never shown: only our own code selects a translated text.
        const code = typeof e.code === 'string' && CODE.test(e.code) ? e.code : 'unknown';
        return { events: [{ type: 'run_error', code }], terminal: true };
      }
      case 'TEXT_MESSAGE_START':
        if (!isId(e.messageId) || (e.role !== undefined && e.role !== 'assistant')) return none;
        if (this.messages.has(e.messageId) || this.messages.size >= MAX_MESSAGES) return none;
        this.messages.set(e.messageId, true);
        return none; // the message appears with its first delta
      case 'TEXT_MESSAGE_CONTENT': {
        if (!isId(e.messageId) || typeof e.delta !== 'string' || e.delta === '' || !this.messages.get(e.messageId)) return none;
        if (this.text + e.delta.length > MAX_TEXT_PER_RUN) return none;
        this.text += e.delta.length;
        return { events: [{ type: 'text_delta', messageId: e.messageId, delta: e.delta }], terminal: false };
      }
      case 'TEXT_MESSAGE_END':
        if (!isId(e.messageId) || !this.messages.get(e.messageId)) return none;
        this.messages.set(e.messageId, false);
        return { events: [{ type: 'text_end', messageId: e.messageId }], terminal: false };
      case 'TOOL_CALL_START': {
        if (!isId(e.toolCallId) || typeof e.toolCallName !== 'string' || !TOOL.test(e.toolCallName)) return none;
        if (this.calls.has(e.toolCallId) || this.calls.size >= MAX_TOOL_CALLS) return none;
        this.calls.set(e.toolCallId, { open: true, tool: e.toolCallName });
        // The wire carries no risk class; show the highest until the server sends it (Q-risk in open-questions).
        return { events: [{ type: 'tool_call', callId: e.toolCallId, tool: e.toolCallName, risk: 'R4' }], terminal: false };
      }
      case 'TOOL_CALL_RESULT': {
        const c = isId(e.toolCallId) ? this.calls.get(e.toolCallId) : undefined;
        if (!c || !c.open || typeof e.content !== 'string' || e.content.length > 20_000) return none;
        c.open = false;
        let outcome: ToolOutcome = 'error';
        try {
          const body = JSON.parse(e.content) as { status?: unknown };
          if (typeof body === 'object' && body !== null && typeof body.status === 'string') {
            outcome = Object.hasOwn(RESULT, body.status) ? RESULT[body.status] : 'error';
          }
        } catch {
          /* unparseable result: shown as an error, never as success */
        }
        return { events: [{ type: 'tool_result', callId: e.toolCallId as string, outcome }], terminal: false };
      }
      case 'CUSTOM': {
        if (e.name !== 'approval.pending') return none; // other allow-listed names have no component yet
        const v = e.value as Record<string, unknown> | null;
        if (typeof v !== 'object' || v === null || !isId(v.approvalId) || typeof v.tool !== 'string' || !TOOL.test(v.tool)) return none;
        if (this.approvals.has(v.approvalId) || this.approvals.size >= 50) return none;
        this.approvals.add(v.approvalId);
        return { events: [{ type: 'approval_pending', approvalId: v.approvalId, tool: v.tool, risk: 'R4' }], terminal: false };
      }
      default:
        return none; // TOOL_CALL_ARGS, state events, Raw, Reasoning, unknown types
    }
  }
}
