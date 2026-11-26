// Record detail view models (WEB-029): line items from child tables, the totals block and the record history. Pure.
// Everything is read from the Blueprint, the tool set and the record; nothing is computed from amounts (numbers come from code).
import { hiddenFields, toolFor, usable } from './access';
import { pick } from './labels';
import { stateOf, stateTone, type Cell, type CellKind, type Tone } from './listModel';
import type { FormModel } from './formModel';
import type { Caller, EntityDef, FieldDef, HistoryEntry, Money, RecordRow, RecordsData } from './types';

const PLAIN_DECIMAL = /^(-?)(\d+)(\.\d+)?$/;

/** Thousands separators on the integer part of a decimal string. The digits are never re-computed (no float maths on money). */
export function groupDigits(value: string): string {
  const m = PLAIN_DECIMAL.exec(value);
  if (!m) return value;
  return `${m[1]}${m[2]!.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}${m[3] ?? ''}`;
}

const NUMERIC = new Set(['integer', 'decimal', 'percent']);
const kindOf = (f: FieldDef): CellKind =>
  f.type === 'money' ? 'money' : NUMERIC.has(f.type) ? 'number' : f.type === 'date' || f.type === 'datetime' ? 'date' : f.type === 'link' ? 'link' : 'text';
const asMoney = (v: unknown): Money | undefined =>
  typeof v === 'object' && v !== null && typeof (v as Money).value === 'string' ? (v as Money) : undefined;

/** The record the caller may open, or nothing (deny by default). */
function openRecord(data: RecordsData, entityId: string, caller: Caller, recordId: string | undefined): { entity: EntityDef; rec: RecordRow } | null {
  const entity = data.entities.find((e) => e.id === entityId);
  if (!entity || !recordId || !usable(toolFor(data.tools, entityId, 'get'), caller)) return null;
  const rec = data.rows[entityId]?.find((r) => r.id === recordId);
  return rec ? { entity, rec } : null;
}

export type LineColumn = { id: string; label: string; kind: CellKind; numeric: boolean };
export type LinesModel = { id: string; title: string; columns: ReadonlyArray<LineColumn>; rows: ReadonlyArray<{ key: string; cells: ReadonlyArray<Cell> }> };

/** One table per child_table relation of the entity, read from the parent record under the relation id. */
export function buildLines(data: RecordsData, entityId: string, caller: Caller, locale: string, recordId?: string): LinesModel[] {
  const open = openRecord(data, entityId, caller, recordId);
  if (!open) return [];
  const hidden = hiddenFields([toolFor(data.tools, entityId, 'get')], caller);
  return (open.entity.relations ?? [])
    .filter((r) => r.kind === 'child_table' && !hidden.has(r.id))
    .flatMap((rel): LinesModel[] => {
      const child = data.entities.find((e) => e.id === rel.target);
      if (!child) return [];
      const fields = child.fields.filter((f) => f.type !== 'attachment');
      const columns = fields.map((f) => {
        const kind = kindOf(f);
        return { id: f.id, label: pick(f.labels, locale, f.id), kind, numeric: kind === 'number' || kind === 'money' };
      });
      const raw = open.rec[rel.id];
      const lines = Array.isArray(raw) ? (raw as ReadonlyArray<Record<string, unknown>>) : [];
      const cellOf = (f: FieldDef, line: Record<string, unknown>): Cell => {
        const kind = kindOf(f);
        const v = line[f.id];
        const m = asMoney(v);
        if (kind === 'money' && m) return { columnId: f.id, kind, text: `${m.value} ${m.currency}`, money: m };
        const s = v === undefined || v === null ? '' : String(v);
        if (kind === 'link' && s && f.target) {
          // The linked record's name only if the caller may open that entity; otherwise its number.
          const may = usable(toolFor(data.tools, f.target, 'get'), caller);
          const target = data.entities.find((e) => e.id === f.target);
          const nameField = target?.fields.find((x) => x.type === 'string' && x.id.endsWith('_name')) ?? target?.fields.find((x) => x.type === 'string');
          const name = may && nameField ? data.rows[f.target]?.find((r) => r.id === s)?.[nameField.id] : undefined;
          return { columnId: f.id, kind, text: typeof name === 'string' && name ? name : s, href: may ? `/records/${f.target}/${s}/` : undefined };
        }
        if (f.type === 'select') return { columnId: f.id, kind, text: pick(f.options?.find((o) => o.value === s)?.labels, locale, s) };
        return { columnId: f.id, kind, text: s };
      };
      return [{
        id: rel.id,
        title: pick(rel.labels ?? child.pluralLabels, locale, rel.id),
        columns,
        rows: lines.map((line, i) => ({ key: `${rel.id}-${i}`, cells: fields.map((f) => cellOf(f, line)) })),
      }];
    });
}

export type TotalLine = { id: string; label: string; value: string; currency: string; grand: boolean };

/**
 * A document's read-only money fields (subtotal, tax, total) read as a totals block under its lines; the last is the grand total.
 * Uses the form model, so hidden fields stay hidden. Master records keep all their fields.
 */
export function splitTotals(data: RecordsData, model: FormModel): { fields: FormModel['fields']; totals: TotalLine[] } {
  const entity = data.entities.find((e) => e.id === model.entityId);
  if (!entity || entity.kind !== 'document' || !model.recordId) return { fields: model.fields, totals: [] };
  const isTotal = (id: string) => {
    const f = entity.fields.find((x) => x.id === id);
    return !!f && f.type === 'money' && (!!f.readOnly || f.computed !== undefined);
  };
  const picked = model.fields.filter((f) => isTotal(f.id));
  return {
    fields: model.fields.filter((f) => !isTotal(f.id)),
    totals: picked.map((f, i) => ({ id: f.id, label: f.label, value: f.value, currency: f.suffix ?? '', grand: i === picked.length - 1 })),
  };
}

export type ActivityItem = { key: string; at: string; by: string; event: HistoryEntry['event']; stateLabel?: string; tone?: Tone };

/** The record's history, newest first, with workflow state labels from the Blueprint. */
export function buildActivity(data: RecordsData, entityId: string, caller: Caller, locale: string, recordId?: string): ActivityItem[] {
  const open = openRecord(data, entityId, caller, recordId);
  if (!open) return [];
  const wf = data.workflows.find((w) => w.id === open.entity.workflow && w.entity === entityId);
  return [...(open.rec.history ?? [])]
    .sort((a, b) => b.at.localeCompare(a.at))
    .map((h, i) => ({
      key: `${h.at}-${i}`, at: h.at, by: h.by, event: h.event,
      ...(h.event === 'state' && h.to ? { stateLabel: pick(stateOf(wf, h.to)?.labels, locale, h.to), tone: stateTone(data, entityId, wf, h.to) } : {}),
    }));
}
