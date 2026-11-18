// Form view model: fields with types, required, read-only and hidden (field_access for the caller's roles). Pure.
import { hiddenFields, readOnlyFields, toolFor, usable } from './access';
import { buildActions, type ActionModel } from './actions';
import { pick } from './labels';
import { stateOf, stateTone, type Tone } from './listModel';
import type { Caller, FieldDef, Money, RecordRow, RecordsData } from './types';

export type FormMode = 'create' | 'edit' | 'view';
export type FieldControl = 'text' | 'numeric' | 'date' | 'select' | 'link' | 'boolean';
export type FormField = {
  id: string;
  label: string;
  control: FieldControl;
  inputType?: 'text' | 'tel' | 'email' | 'date';
  required: boolean;
  readOnly: boolean;
  value: string;
  suffix?: string; // currency code for money
  maxLength?: number;
  options?: ReadonlyArray<{ value: string; label: string }>;
};
export type FormModel = {
  entityId: string;
  mode: FormMode;
  title: string;
  recordId?: string;
  stateLabel?: string;
  stateTone?: Tone;
  state?: string;
  fields: ReadonlyArray<FormField>;
  /** The save action (create or edit) when the mode is writable; absent in view mode. */
  saveAction?: ActionModel;
  /** Every other action offered for this record (submit, cancel, amend, transitions). */
  actions: ReadonlyArray<ActionModel>;
};

const NUMERIC = new Set(['integer', 'decimal', 'percent', 'money', 'phone']);

export function buildFormModel(data: RecordsData, entityId: string, caller: Caller, locale: string, recordId?: string): FormModel | null {
  const entity = data.entities.find((e) => e.id === entityId);
  if (!entity) return null;
  const rec: RecordRow | undefined = recordId ? data.rows[entityId]?.find((r) => r.id === recordId) : undefined;
  if (recordId && !rec) return null;
  const wf = data.workflows.find((w) => w.id === entity.workflow && w.entity === entityId);
  const tool = (v: string) => toolFor(data.tools, entityId, v);
  const actions = buildActions({ entity, workflow: wf, tools: data.tools, caller, record: rec });
  const save = rec ? actions.find((a) => a.kind === 'edit') : actions.find((a) => a.kind === 'create');
  const canView = usable(tool('get'), caller);
  const found: FormMode | null = save ? (rec ? 'edit' : 'create') : rec && canView ? 'view' : null;
  if (!found) return null;
  const mode: FormMode = found; // deny by default: no create/update/get tool for this caller

  const hidden = hiddenFields([tool('get'), tool('list'), tool('create'), tool('update')], caller);
  const ro = readOnlyFields([tool(rec ? 'update' : 'create')], caller);
  const fieldOf = (f: FieldDef): FormField | null => {
    if (hidden.has(f.id) || f.type === 'attachment') return null;
    const computed = f.readOnly || f.computed !== undefined;
    if (!rec && computed) return null; // computed values are never input; they appear once the record exists
    const m = rec?.[f.id] as Money | undefined;
    const raw = rec?.[f.id];
    const value = f.type === 'money' ? (m?.value ?? '') : raw === undefined || raw === null ? '' : String(raw);
    const target = f.type === 'link' && f.target ? data.entities.find((e) => e.id === f.target) : undefined;
    const linkable = target && usable(toolFor(data.tools, target.id, 'list'), caller);
    const nameField = target?.fields.find((x) => x.type === 'string');
    const control: FieldControl =
      f.type === 'select' ? 'select' : f.type === 'link' ? (linkable ? 'link' : 'text') : f.type === 'boolean' ? 'boolean'
      : f.type === 'date' || f.type === 'datetime' ? 'date' : NUMERIC.has(f.type) ? 'numeric' : 'text';
    return {
      id: f.id, label: pick(f.labels, locale, f.id), control, required: !!f.required,
      readOnly: mode === 'view' || computed || ro.has(f.id) || (f.type === 'link' && !linkable),
      value, maxLength: f.maxLength,
      inputType: f.type === 'phone' ? 'tel' : f.type === 'email' ? 'email' : control === 'date' ? 'date' : 'text',
      suffix: f.type === 'money' ? (m?.currency ?? undefined) : undefined,
      options:
        control === 'select' ? f.options?.map((o) => ({ value: o.value, label: pick(o.labels, locale, o.value) }))
        : control === 'link' ? (data.rows[target!.id] ?? []).map((r) => ({ value: r.id, label: `${r.id}${nameField && typeof r[nameField.id] === 'string' ? ` - ${r[nameField.id]}` : ''}` }))
        : undefined,
    };
  };
  const state = stateOf(wf, rec?.state);
  return {
    entityId, mode, recordId, state: rec?.state, stateTone: state ? stateTone(data, entityId, wf, state.id) : undefined, stateLabel: state ? pick(state.labels, locale, state.id) : undefined,
    title: pick(entity.labels, locale, entity.id),
    fields: entity.fields.map(fieldOf).filter((f): f is FormField => f !== null),
    saveAction: save, actions: actions.filter((a) => a !== save),
  };
}
