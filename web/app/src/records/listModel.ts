// List view model: columns, filters, search, sort, pagination and linked-record cells. Pure.
import { hiddenFields, toolFor, usable } from './access';
import { buildActions, type ActionModel } from './actions';
import { pick } from './labels';
import type { Caller, EntityDef, FieldDef, Money, RecordRow, RecordsData, StateDef, WorkflowDef } from './types';

export type ListQuery = {
  search: string;
  filters: Readonly<Record<string, string>>;
  sort?: { field: string; direction: 'asc' | 'desc' };
  page: number; // 1-based
  pageSize: number;
};
export const defaultQuery: ListQuery = { search: '', filters: {}, page: 1, pageSize: 5 };

export type CellKind = 'text' | 'number' | 'money' | 'date' | 'link' | 'status';
export type Column = {
  id: string;
  label: string;
  kind: CellKind;
  numeric: boolean;
  sortable: boolean;
  /** A select filter when the column has a closed set of values. */
  filter?: { options: ReadonlyArray<{ value: string; label: string }> };
};
export type Tone = 'success' | 'warning' | 'danger' | 'neutral';
export type Cell = { columnId: string; kind: CellKind; text: string; money?: Money; href?: string; state?: string; tone?: Tone };
export type ListRow = { id: string; href?: string; cells: ReadonlyArray<Cell> };

export type ListModel = {
  entityId: string;
  title: string;
  columns: ReadonlyArray<Column>;
  rows: ReadonlyArray<ListRow>;
  total: number;
  page: number;
  pageCount: number;
  query: ListQuery;
  createAction?: ActionModel;
};

const NUMERIC = new Set(['integer', 'decimal', 'percent']);
const asMoney = (v: unknown): Money | undefined =>
  typeof v === 'object' && v !== null && typeof (v as Money).value === 'string' ? (v as Money) : undefined;

/** The label of a linked record: its first string field, else its id. */
const display = (target: EntityDef | undefined, row: RecordRow | undefined, id: string): string => {
  const f = target?.fields.find((x) => x.type === 'string');
  const v = f && row ? row[f.id] : undefined;
  return typeof v === 'string' && v ? v : id;
};

export const stateOf = (wf: WorkflowDef | undefined, id: string | undefined): StateDef | undefined =>
  wf?.states.find((s) => s.id === id);

/** Initial states are neutral, in-progress warning, final success; a state reached by cancel or reversal is danger. */
export function stateTone(data: RecordsData, entityId: string, wf: WorkflowDef | undefined, stateId: string | undefined): Tone {
  const st = stateOf(wf, stateId);
  if (!st) return 'neutral';
  const cancelled = data.tools.some((t) => t.entity === entityId && t.transitions?.some((x) => x.to === st.id && ['cancel', 'cancel_draft', 'reversal'].includes(x.kind)));
  return cancelled ? 'danger' : st.kind === 'final' ? 'success' : st.kind === 'initial' ? 'neutral' : 'warning';
}

export function buildListModel(data: RecordsData, entityId: string, caller: Caller, locale: string, query: ListQuery = defaultQuery): ListModel | null {
  const entity = data.entities.find((e) => e.id === entityId);
  const list = toolFor(data.tools, entityId, 'list');
  if (!entity || !usable(list, caller)) return null; // deny by default
  const get = toolFor(data.tools, entityId, 'get');
  const hidden = hiddenFields([list, get], caller);
  const wf = data.workflows.find((w) => w.id === entity.workflow && w.entity === entityId);
  const fields = entity.fields.filter((f) => !hidden.has(f.id) && f.type !== 'attachment');

  const cellKind = (f: FieldDef): CellKind =>
    f.type === 'money' ? 'money' : NUMERIC.has(f.type) ? 'number' : f.type === 'date' || f.type === 'datetime' ? 'date' : f.type === 'link' ? 'link' : 'text';
  const columns: Column[] = fields.map((f) => {
    const kind = cellKind(f);
    return {
      id: f.id, label: pick(f.labels, locale, f.id), kind, numeric: kind === 'number' || kind === 'money', sortable: true,
      filter: f.type === 'select' && f.options ? { options: f.options.map((o) => ({ value: o.value, label: pick(o.labels, locale, o.value) })) } : undefined,
    };
  });
  if (wf) {
    columns.push({
      id: 'state', label: '', kind: 'status', numeric: false, sortable: true,
      filter: { options: wf.states.map((s) => ({ value: s.id, label: pick(s.labels, locale, s.id) })) },
    });
  }

  const linkTarget = (f: FieldDef) => data.entities.find((e) => e.id === f.target);
  const linkOpen = (f: FieldDef) => (f.target && usable(toolFor(data.tools, f.target, 'get'), caller) ? f.target : undefined);
  const optLabel = (f: FieldDef, v: string) => pick(f.options?.find((o) => o.value === v)?.labels, locale, v);

  const toRow = (r: RecordRow): ListRow => ({
    id: r.id,
    href: get && usable(get, caller) ? `/records/${entityId}/${r.id}/` : undefined,
    cells: columns.map((c): Cell => {
      if (c.id === 'state') return { columnId: c.id, kind: 'status', text: pick(stateOf(wf, r.state)?.labels, locale, r.state ?? ''), state: r.state, tone: stateTone(data, entityId, wf, r.state) };
      const f = fields.find((x) => x.id === c.id)!;
      const raw = r[f.id];
      const m = asMoney(raw);
      if (c.kind === 'money' && m) return { columnId: c.id, kind: 'money', text: `${m.value} ${m.currency}`, money: m };
      const s = raw === undefined || raw === null ? '' : String(raw);
      if (c.kind === 'link' && s) {
        const t = linkTarget(f);
        const open = linkOpen(f);
        // The linked record's name is shown only if the caller may open that entity; otherwise just its id.
        return { columnId: c.id, kind: 'link', text: open ? display(t, data.rows[open]?.find((x) => x.id === s), s) : s, href: open ? `/records/${open}/${s}/` : undefined };
      }
      return { columnId: c.id, kind: c.kind, text: f.type === 'select' ? optLabel(f, s) : s };
    }),
  });

  // Filter, search and sort run on what the caller may see: hidden fields cannot be probed through them.
  const all = (data.rows[entityId] ?? []).map(toRow);
  const raw = new Map((data.rows[entityId] ?? []).map((r) => [r.id, r]));
  const needle = query.search.trim().toLowerCase();
  const filtered = all.filter((row) => {
    const rec = raw.get(row.id)!;
    for (const [col, val] of Object.entries(query.filters)) {
      const c = columns.find((x) => x.id === col);
      if (!c?.filter || !val) continue; // unknown or unfilterable column: ignored
      if (String(rec[col] ?? '') !== val) return false;
    }
    if (!needle) return true;
    return row.id.toLowerCase().includes(needle) || row.cells.some((c) => c.text.toLowerCase().includes(needle));
  });
  const sortCol = columns.find((c) => c.id === query.sort?.field && c.sortable);
  if (sortCol && query.sort) {
    const dir = query.sort.direction === 'desc' ? -1 : 1;
    const key = (row: ListRow) => {
      const c = row.cells.find((x) => x.columnId === sortCol.id)!;
      return c.money ? Number(c.money.value) : sortCol.kind === 'number' ? Number(c.text) : c.text;
    };
    filtered.sort((a, b) => {
      const x = key(a), y = key(b);
      return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), locale)) * dir;
    });
  }
  const pageSize = Math.max(1, query.pageSize);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const page = Math.min(Math.max(1, query.page), pageCount);
  return {
    entityId, title: pick(entity.pluralLabels, locale, entity.id), columns, total: filtered.length, page, pageCount, query: { ...query, page, pageSize },
    rows: filtered.slice((page - 1) * pageSize, page * pageSize),
    createAction: buildActions({ entity, tools: data.tools, caller }).find((a) => a.kind === 'create'),
  };
}
