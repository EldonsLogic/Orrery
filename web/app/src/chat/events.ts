import { RISKS, type ChatEvent, type RiskClass, type ToolOutcome } from './types';

const OUTCOMES: ReadonlyArray<ToolOutcome> = ['ok', 'denied', 'error', 'pending_approval'];
const str = (v: unknown, max = 500): v is string => typeof v === 'string' && v.length > 0 && v.length <= max;
const risk = (v: unknown): v is RiskClass => (RISKS as ReadonlyArray<unknown>).includes(v);

/** Allow-list validator for the wire shape: returns null for unknown types or bad fields (never throws). */
export function parseChatEvent(raw: unknown): ChatEvent | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const e = raw as Record<string, unknown>;
  switch (e.type) {
    case 'run_started':
      return str(e.runId) ? { type: 'run_started', runId: e.runId } : null;
    case 'text_delta':
      return str(e.messageId) && typeof e.delta === 'string' && e.delta.length <= 20000 ? { type: 'text_delta', messageId: e.messageId, delta: e.delta } : null;
    case 'text_end':
      return str(e.messageId) ? { type: 'text_end', messageId: e.messageId } : null;
    case 'tool_call':
      return str(e.callId) && str(e.tool) && risk(e.risk) ? { type: 'tool_call', callId: e.callId, tool: e.tool, risk: e.risk } : null;
    case 'tool_result':
      return str(e.callId) && OUTCOMES.includes(e.outcome as ToolOutcome) ? { type: 'tool_result', callId: e.callId, outcome: e.outcome as ToolOutcome } : null;
    case 'confirm_required': {
      if (!str(e.confirmId) || !str(e.tool) || !risk(e.risk) || !Array.isArray(e.changes) || e.changes.length > 50) return null;
      const changes = [];
      for (const c of e.changes as unknown[]) {
        const o = c as Record<string, unknown>;
        if (typeof o !== 'object' || o === null || !str(o.label) || typeof o.before !== 'string' || typeof o.after !== 'string') return null;
        changes.push({ label: o.label, before: o.before, after: o.after });
      }
      return { type: 'confirm_required', confirmId: e.confirmId, tool: e.tool, risk: e.risk, changes };
    }
    case 'approval_pending':
      return str(e.approvalId) && str(e.tool) && risk(e.risk) ? { type: 'approval_pending', approvalId: e.approvalId, tool: e.tool, risk: e.risk } : null;
    case 'abstain':
      return str(e.clarifyKey, 100) ? { type: 'abstain', clarifyKey: e.clarifyKey } : null;
    case 'run_error':
      return str(e.code, 100) ? { type: 'run_error', code: e.code } : null;
    case 'run_finished':
      return e.outcome === 'done' || e.outcome === 'interrupt' || e.outcome === 'cancelled' ? { type: 'run_finished', outcome: e.outcome } : null;
    default:
      return null;
  }
}
