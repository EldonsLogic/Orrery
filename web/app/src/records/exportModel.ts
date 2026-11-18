// Bulk export view model (WEB-024): the columns and rows the caller may see, as text. Pure.
// Hidden fields (field_access, any of the caller's roles) never appear. No list tool for the caller means no export.
import { hiddenFields, toolFor, usable } from './access';
import { toCsv } from './csv';
import { pick } from './labels';
import type { Caller, Money, RecordsData } from './types';

export type ExportModel = {
  entityId: string;
  title: string;
  fileName: string;
  headers: ReadonlyArray<string>;
  rows: ReadonlyArray<ReadonlyArray<string>>;
  csv: string;
};

export function buildExportModel(data: RecordsData, entityId: string, caller: Caller, locale: string, idHeader: string): ExportModel | null {
  const entity = data.entities.find((e) => e.id === entityId);
  const list = toolFor(data.tools, entityId, 'list');
  if (!entity || !usable(list, caller)) return null;
  const hidden = hiddenFields([list, toolFor(data.tools, entityId, 'get'), toolFor(data.tools, entityId, 'export')], caller);
  const fields = entity.fields.filter((f) => !hidden.has(f.id) && f.type !== 'attachment');
  const cell = (v: unknown): string =>
    v === undefined || v === null ? '' : typeof v === 'object' ? ((v as Money).value ?? '') : String(v);
  const headers = [idHeader, ...fields.map((f) => pick(f.labels, locale, f.id))];
  const rows = (data.rows[entityId] ?? []).map((r) => [r.id, ...fields.map((f) => cell(r[f.id]))]);
  return { entityId, title: pick(entity.labels, locale, entity.id), fileName: `${entityId}.csv`, headers, rows, csv: toCsv([headers, ...rows]) };
}
