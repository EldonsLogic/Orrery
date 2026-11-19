// Bulk import model (WEB-024): column mapping, per-row validation, preview and error report. Pure; writes nothing.
// Which fields may be imported follows the create tool's field_access for the caller's roles (deny by default).
// The same rules apply as in the form: hidden, read-only and computed fields are never importable.
import { hiddenFields, readOnlyFields, toolFor, usable } from './access';
import { executable, modeFor, type ActionModel } from './actions';
import { csvCell } from './csv';
import { pick } from './labels';
import type { Caller, EntityDef, FieldDef, RecordsData, RiskClass } from './types';

export const MAX_IMPORT_ROWS = 5000;
export const MAX_IMPORT_BYTES = 2_000_000;

export type ImportField = { id: string; label: string; type: string; required: boolean; options?: ReadonlyArray<{ value: string; labels: Readonly<Record<string, string>> }>; maxLength?: number; precision?: number; target?: string };
export type ImportPlan = {
  entityId: string;
  title: string;
  fields: ReadonlyArray<ImportField>;
  /** Required fields the caller cannot fill (hidden or read-only for them): the import cannot run at all. */
  blockedRequired: ReadonlyArray<string>;
  /** The bulk write: always asks first (R2 at least). Absent when the caller has no create tool. */
  action?: ActionModel;
};

const RISK_ORDER: RiskClass[] = ['R0', 'R1', 'R2', 'R3', 'R4'];
const atLeastR2 = (r: RiskClass): RiskClass => (RISK_ORDER.indexOf(r) < 2 ? 'R2' : r);

export function buildImportPlan(data: RecordsData, entityId: string, caller: Caller, locale: string): ImportPlan | null {
  const entity: EntityDef | undefined = data.entities.find((e) => e.id === entityId);
  const create = toolFor(data.tools, entityId, 'create');
  if (!entity || !usable(create, caller)) return null;
  const hidden = hiddenFields([create, toolFor(data.tools, entityId, 'get'), toolFor(data.tools, entityId, 'list')], caller);
  const ro = readOnlyFields([create], caller);
  const fields: ImportField[] = [];
  const blocked: string[] = [];
  for (const f of entity.fields as ReadonlyArray<FieldDef>) {
    if (f.type === 'attachment' || f.readOnly || f.computed !== undefined) continue; // never input
    const target = f.type === 'link' && f.target ? f.target : undefined;
    const linkOk = !target || usable(toolFor(data.tools, target, 'list'), caller);
    if (hidden.has(f.id) || ro.has(f.id) || !linkOk) { if (f.required) blocked.push(pick(f.labels, locale, f.id)); continue; }
    fields.push({ id: f.id, label: pick(f.labels, locale, f.id), type: f.type, required: !!f.required, options: f.options, maxLength: f.maxLength, precision: f.precision, target });
  }
  // Bulk create is R2 at least; needs_approval stays needs_approval.
  const risk = atLeastR2(create.risk_class);
  const action: ActionModel = {
    id: 'bulk_import', kind: 'create', tool: create.name, risk,
    mode: modeFor(risk, create.agent_creatable),
    effects: { ledger: !!create.effects?.ledger, tax: !!create.effects?.tax, externalSend: !!create.effects?.external_send },
  };
  return { entityId, title: pick(entity.labels, locale, entity.id), fields, blockedRequired: blocked, action };
}

export const canRunImport = (p: ImportPlan): boolean => !!p.action && executable(p.action) && p.blockedRequired.length === 0;

// ---- mapping ----
const norm = (s: string): string => s.normalize('NFKC').trim().toLowerCase().replace(/[\s_-]+/g, ' ');

/** Header text to field: by id or by label in any locale. Unmatched headers map to null (skipped). Each field is used once. */
export function autoMap(headers: ReadonlyArray<string>, plan: ImportPlan, data: RecordsData): Array<string | null> {
  const entity = data.entities.find((e) => e.id === plan.entityId);
  const names = new Map<string, string>();
  for (const f of plan.fields) {
    names.set(norm(f.id), f.id);
    for (const l of Object.values(entity?.fields.find((x) => x.id === f.id)?.labels ?? {})) names.set(norm(l), f.id);
  }
  const used = new Set<string>();
  return headers.map((h) => {
    const id = names.get(norm(h));
    if (!id || used.has(id)) return null;
    used.add(id);
    return id;
  });
}

export type MappingIssue = { code: 'duplicate' | 'missingRequired'; fieldId: string };
export function checkMapping(mapping: ReadonlyArray<string | null>, plan: ImportPlan): MappingIssue[] {
  const issues: MappingIssue[] = [];
  const seen = new Set<string>();
  for (const m of mapping) {
    if (!m) continue;
    if (seen.has(m)) issues.push({ code: 'duplicate', fieldId: m });
    seen.add(m);
  }
  for (const f of plan.fields) if (f.required && !seen.has(f.id)) issues.push({ code: 'missingRequired', fieldId: f.id });
  return issues;
}

// ---- validation ----
export type ErrorCode = 'required' | 'tooLong' | 'notNumber' | 'notInteger' | 'tooPrecise' | 'notDate' | 'notBoolean' | 'notOption' | 'notLink' | 'notEmail' | 'notPhone';
export type RowError = { fieldId: string; code: ErrorCode; value: string };
export type PreviewRow = { line: number; values: Record<string, string>; errors: ReadonlyArray<RowError> };
export type ImportPreview = { rows: ReadonlyArray<PreviewRow>; validCount: number; invalidCount: number };

const AR_DIGITS = '٠١٢٣٤٥٦٧٨٩';
/** Arabic-Indic digits and separators to Latin, so a file typed in Arabic still validates. */
export const normalizeDigits = (s: string): string =>
  s.replace(/[٠-٩]/g, (c) => String(AR_DIGITS.indexOf(c))).replace(/٫/g, '.').replace(/٬/g, ',');

const TRUE = new Set(['true', 'yes', 'y', '1', 'نعم']);
const FALSE = new Set(['false', 'no', 'n', '0', 'لا']);

const validDate = (s: string): boolean => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return false;
  const d = new Date(Date.UTC(+m[1]!, +m[2]! - 1, +m[3]!));
  return d.getUTCFullYear() === +m[1]! && d.getUTCMonth() === +m[2]! - 1 && d.getUTCDate() === +m[3]!;
};

/** Validates one cell. Returns the cleaned value or an error code. Empty optional cells are valid and stay empty. */
export function checkCell(f: ImportField, raw: string, data: RecordsData): { value: string } | { code: ErrorCode } {
  const text = raw.trim();
  if (text === '') return f.required ? { code: 'required' } : { value: '' };
  switch (f.type) {
    case 'integer': {
      const v = normalizeDigits(text);
      return /^-?\d+$/.test(v) ? { value: v } : { code: 'notInteger' };
    }
    case 'decimal': case 'percent': case 'money': {
      let v = normalizeDigits(text);
      if (/^-?\d{1,3}(,\d{3})+(\.\d+)?$/.test(v)) v = v.replace(/,/g, '');
      if (!/^-?\d+(\.\d+)?$/.test(v)) return { code: 'notNumber' };
      if (f.precision !== undefined && (v.split('.')[1]?.length ?? 0) > f.precision) return { code: 'tooPrecise' };
      return { value: v };
    }
    case 'boolean': {
      const v = text.toLowerCase();
      return TRUE.has(v) ? { value: 'true' } : FALSE.has(v) ? { value: 'false' } : { code: 'notBoolean' };
    }
    case 'date': {
      const v = normalizeDigits(text);
      return validDate(v) ? { value: v } : { code: 'notDate' };
    }
    case 'datetime': {
      const v = normalizeDigits(text);
      return validDate(v.slice(0, 10)) && /^.{10}([T ]\d{2}:\d{2}(:\d{2})?)?$/.test(v) ? { value: v } : { code: 'notDate' };
    }
    case 'select': {
      const hit = f.options?.find((o) => o.value === text || Object.values(o.labels).some((l) => norm(l) === norm(text)));
      return hit ? { value: hit.value } : { code: 'notOption' };
    }
    case 'link':
      return f.target && data.rows[f.target]?.some((r) => r.id === text) ? { value: text } : { code: 'notLink' };
    case 'email': return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text) ? { value: text } : { code: 'notEmail' };
    case 'phone': {
      const v = normalizeDigits(text);
      return /^\+?[0-9 ()-]{7,20}$/.test(v) ? { value: v } : { code: 'notPhone' };
    }
    default:
      return f.maxLength !== undefined && text.length > f.maxLength ? { code: 'tooLong' } : { value: text };
  }
}

/** `body` is the file without its header row; `firstLine` is the 1-based file line of body[0]. */
export function validateRows(
  body: ReadonlyArray<ReadonlyArray<string>>, mapping: ReadonlyArray<string | null>, plan: ImportPlan, data: RecordsData, firstLine = 2,
): ImportPreview {
  const byId = new Map(plan.fields.map((f) => [f.id, f]));
  const rows: PreviewRow[] = body.map((cells, i) => {
    const values: Record<string, string> = {};
    const errors: RowError[] = [];
    for (const f of plan.fields) values[f.id] = '';
    mapping.forEach((fid, col) => {
      const f = fid ? byId.get(fid) : undefined;
      if (!f) return;
      const raw = cells[col] ?? '';
      const r = checkCell(f, raw, data);
      if ('code' in r) errors.push({ fieldId: f.id, code: r.code, value: raw });
      else values[f.id] = r.value;
    });
    return { line: firstLine + i, values, errors };
  });
  const invalidCount = rows.filter((r) => r.errors.length > 0).length;
  return { rows, validCount: rows.length - invalidCount, invalidCount };
}

/** Rows that will be sent on confirm: only the valid ones, only mapped fields, only fields the plan allows. */
export const validValues = (p: ImportPreview): Array<Record<string, string>> => p.rows.filter((r) => r.errors.length === 0).map((r) => r.values);

/** Error report as CSV text: one line per problem (file line, field, problem, the value as typed). */
export function errorReportCsv(
  preview: ImportPreview, labelOf: (fieldId: string) => string, describe: (code: ErrorCode) => string,
  header: { line: string; field: string; problem: string; value: string },
): string {
  const lines = [[header.line, header.field, header.problem, header.value]];
  for (const r of preview.rows) for (const e of r.errors) lines.push([String(r.line), labelOf(e.fieldId), describe(e.code), e.value]);
  return lines.map((l) => l.map(csvCell).join(',')).join('\r\n') + '\r\n';
}
