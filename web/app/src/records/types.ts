// WEB-023: types for the generic record screens. Inputs are data (Blueprint entity, Tool API definitions, caller);
// nothing here reads the browser, a network or a store.
export type Loc = Readonly<Record<string, string>>;
export type RiskClass = 'R0' | 'R1' | 'R2' | 'R3' | 'R4';

export type FieldDef = {
  id: string;
  type: string; // Blueprint field type: string, text, integer, decimal, money, percent, boolean, date, select, link, phone, email ...
  labels: Loc;
  required?: boolean;
  readOnly?: boolean;
  computed?: unknown;
  target?: string;
  options?: ReadonlyArray<{ value: string; labels: Loc }>;
  maxLength?: number;
  precision?: number;
};

/** A Blueprint relation; `child_table` rows live on the parent record under the relation id (line items). */
export type RelationDef = { id: string; target: string; cardinality: string; kind?: string; labels?: Loc };
export type EntityDef = {
  id: string; labels: Loc; pluralLabels: Loc; kind: string; fields: ReadonlyArray<FieldDef>; workflow?: string; relations?: ReadonlyArray<RelationDef>;
};
export type StateDef = { id: string; kind?: string; locksEditing?: boolean; labels: Loc };
export type WorkflowDef = { id: string; entity: string; states: ReadonlyArray<StateDef> };
export type RoleDef = { id: string; labels: Loc; scope: { type: string; values?: ReadonlyArray<string> } };

export type TransitionDef = {
  id: string;
  from: string;
  to: string;
  kind: string; // advance, approve, reject, cancel, reversal, cancel_draft
  risk_class: RiskClass;
  agent_creatable: boolean;
  allowed_roles: ReadonlyArray<string>;
  labels: Loc;
};

export type ToolDef = {
  name: string; // <entity>.<verb>
  kind: 'read' | 'write' | 'admin';
  risk_class: RiskClass;
  agent_creatable: boolean;
  entity: string;
  labels: Loc;
  requires: { roles: ReadonlyArray<string>; scopes_by_role: Readonly<Record<string, unknown>> };
  approval: { required: boolean; rule: string | null; agent_required: boolean };
  effects?: { ledger: boolean; tax: boolean; external_send: boolean };
  field_access?: {
    hidden_by_role: Readonly<Record<string, ReadonlyArray<string>>>;
    read_only_by_role: Readonly<Record<string, ReadonlyArray<string>>>;
  };
  transitions?: ReadonlyArray<TransitionDef>;
};

/** Who is looking, passed in as data by the shell (session, later PLT-005). Never read from the browser. */
export type Caller = { roleIds: ReadonlyArray<string> };

export type Money = { value: string; currency: string };
/** One entry of a record's history: who did what, when. Fixture-only until the gateway serves record history (Q-682). */
export type HistoryEntry = { at: string; by: string; event: 'created' | 'updated' | 'state'; to?: string };
export type RecordRow = { id: string; state?: string; history?: ReadonlyArray<HistoryEntry> } & Record<string, unknown>;

export type RecordsData = {
  entities: ReadonlyArray<EntityDef>;
  workflows: ReadonlyArray<WorkflowDef>;
  tools: ReadonlyArray<ToolDef>;
  rows: Readonly<Record<string, ReadonlyArray<RecordRow>>>;
};

export type ActionKind = 'create' | 'edit' | 'amend' | 'submit' | 'cancel' | 'transition';
/** direct: run now. confirm: show a summary, then run. needs_approval: shown, never executed by the UI. */
export type ActionMode = 'direct' | 'confirm' | 'needs_approval';
