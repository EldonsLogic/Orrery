import { MAX_SOURCES, RISKS, type ChatEvent, type RiskClass, type SourceRef, type ToolOutcome } from './types';

const OUTCOMES: ReadonlyArray<ToolOutcome> = ['ok', 'denied', 'error', 'pending_approval'];
const str = (v: unknown, max = 500): v is string => typeof v === 'string' && v.length > 0 && v.length <= max;
const risk = (v: unknown): v is RiskClass => (RISKS as ReadonlyArray<unknown>).includes(v);
// Source records: an entity id (Blueprint style) and a record id (document numbers such as SO-00001). Nothing else passes.
const ENTITY = /^[a-z][a-z0-9_]{0,47}$/;
const RECORD = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/;

/** Validates a source list: at most MAX_SOURCES, each well-formed, duplicates dropped; null when anything is malformed. */
export function parseSources(raw: unknown): SourceRef[] | null {
  if (!Array.isArray(raw) || raw.length > MAX_SOURCES) return null;
  const out: SourceRef[] = [];
  for (const r of raw as unknown[]) {
    const o = r as Record<string, unknown>;
    if (typeof o !== 'object' || o === null || typeof o.entity !== 'string' || typeof o.id !== 'string') return null;
    if (!ENTITY.test(o.entity) || !RECORD.test(o.id)) return null;
    if (!out.some((x) => x.entity === o.entity && x.id === o.id)) out.push({ entity: o.entity, id: o.id });
  }
  return out;
}

/** An optional record reference: undefined when absent, null when malformed (the whole event is then dropped). */
const recordOf = (raw: unknown): SourceRef | undefined | null => {
  if (raw === undefined) return undefined;
  return parseSources([raw])?.[0] ?? null;
};

/** The route of a source record. Both parts are validated above; the id is still encoded. */
export const sourceHref = (s: SourceRef): string => `/records/${s.entity}/${encodeURIComponent(s.id)}/`;

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
    case 'sources': {
      const records = str(e.messageId) ? parseSources(e.records) : null;
      return records ? { type: 'sources', messageId: e.messageId as string, records } : null;
    }
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
        if (o.field !== undefined && !(typeof o.field === 'string' && ENTITY.test(o.field))) return null;
        changes.push(o.field ? { field: o.field as string, label: o.label, before: o.before, after: o.after } : { label: o.label, before: o.before, after: o.after });
      }
      const rec = recordOf(e.record);
      if (rec === null) return null;
      return { type: 'confirm_required', confirmId: e.confirmId, tool: e.tool, risk: e.risk, changes, ...(rec ? { record: rec } : {}) };
    }
    case 'approval_pending': {
      const rec = recordOf(e.record);
      if (!str(e.approvalId) || !str(e.tool) || !risk(e.risk) || rec === null) return null;
      return { type: 'approval_pending', approvalId: e.approvalId, tool: e.tool, risk: e.risk, ...(rec ? { record: rec } : {}) };
    }
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
