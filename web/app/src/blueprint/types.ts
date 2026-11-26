// DSC-007: the slice of the Blueprint contract the owner viewer reads, and the view-model it produces.
// The view-model carries i18n keys and data only: no sentence is built in code, and nothing here names
// the engine, a component id or a tool name beyond what the Blueprint itself says.
export type Loc = Readonly<Record<string, string>>;

export type BpField = { id: string; type: string; labels: Loc; required?: boolean; readOnly?: boolean; computed?: unknown; options?: ReadonlyArray<{ value: string; labels: Loc }> };
export type BpEntity = {
  id: string;
  labels: Loc;
  pluralLabels: Loc;
  kind: string;
  fields: ReadonlyArray<BpField>;
  workflow?: string;
  numbering?: { prefix?: string; padding?: number; resetPerFiscalYear?: boolean };
};
export type BpGuard = { field: string; op: string; value?: unknown };
export type BpState = { id: string; kind?: string; locksEditing?: boolean; labels: Loc };
export type BpTransition = { id: string; from: string; to: string; actionLabels: Loc; allowedRoles: ReadonlyArray<string>; guards?: ReadonlyArray<BpGuard>; approval?: string; notify?: ReadonlyArray<string> };
export type BpWorkflow = { id: string; entity: string; labels: Loc; states: ReadonlyArray<BpState>; transitions: ReadonlyArray<BpTransition> };
export type BpPermission = { entity: string; actions: ReadonlyArray<string>; hiddenFields?: ReadonlyArray<string>; readOnlyFields?: ReadonlyArray<string> };
export type BpRole = { id: string; labels: Loc; function: string; scope: { type: string; values?: ReadonlyArray<string> }; permissions?: ReadonlyArray<BpPermission>; isAdmin?: boolean };
export type BpApproval = { id: string; labels: Loc; appliesTo: { entity: string; action: string }; conditions?: ReadonlyArray<BpGuard>; steps: ReadonlyArray<{ order: number; approverRole: string; timeoutHours?: number }> };
export type BpLocation = { id: string; kind: string; labels: Loc; city?: string };
export type BpAssistant = {
  id: string;
  department: string;
  labels: Loc;
  roles: ReadonlyArray<string>;
  tools: ReadonlyArray<{ tool: string; confirm?: boolean; transitions?: ReadonlyArray<string> }>;
  limits: { perCall: { maxToolCalls: number; maxRows: number }; perDay: { maxToolCalls: number; maxWrites: number } };
  memory: { scope: string; retentionDays?: number };
};
export type BpCompany = {
  legalName: Loc;
  tradeName?: Loc;
  country: string;
  crNumber?: string;
  vatNumber?: string;
  sizeBand?: string;
  industry?: string;
  languages: { primary: string; secondary?: ReadonlyArray<string> };
  locale: {
    timezone: string;
    calendar: { primary: string; secondaryDisplay?: string };
    week: { startDay: string; weekendDays: ReadonlyArray<string> };
    workingTime?: { workDays: ReadonlyArray<string>; hours: { from: string; to: string }; reducedPeriods?: ReadonlyArray<{ id: string; labels: Loc; hours: { from: string; to: string } }> };
    fiscalYear: { type: string; startMonth: number; startDay: number };
    holidays?: { overrides?: ReadonlyArray<unknown> };
    numberSystem: string;
    currency: string;
  };
};
export type BpCompliance = {
  country: string;
  countryPack?: { id: string; version: string };
  eInvoicing?: { mode: string; environment?: string };
  vat?: { registered: boolean; defaultRatePercent?: number; filingPeriod?: string; pricesIncludeVat?: boolean };
  payroll?: { wpsEnabled?: boolean };
};
export type Blueprint = {
  meta: { id: string; schemaVersion: string; revision: number; buildState: string; updatedAt: string };
  company: BpCompany;
  locations: ReadonlyArray<BpLocation>;
  entities: ReadonlyArray<BpEntity>;
  workflows?: ReadonlyArray<BpWorkflow>;
  roles: ReadonlyArray<BpRole>;
  approvals?: ReadonlyArray<BpApproval>;
  compliance: BpCompliance;
  assistants?: ReadonlyArray<BpAssistant>;
};

/** One diff operation, the subset of services/blueprint/diff `diff.schema.json` the summary reads. */
export type DiffImpact = 'cosmetic' | 'config' | 'data_shape' | 'destructive' | 'compliance' | 'access' | 'branding';
export type DiffOp = {
  op: 'add' | 'remove' | 'replace' | 'reorder';
  impact: DiffImpact;
  schemaPath: string;
  subject: { kind: string; id: string };
  labels?: { before: Loc | null; after: Loc | null } | null;
};

export type Caller = { roleIds: ReadonlyArray<string> };

/** An i18n key under `blueprint.` plus ICU params (data values only). */
export type Msg = { key: string; params?: Readonly<Record<string, string | number | Msg>> };
export const msg = (key: string, params?: Msg['params']): Msg => (params ? { key, params } : { key });

export type Badges = { draft: boolean; unverified: boolean };

export type RoleRow = { id: string; label: string; scope: Msg; rules: ReadonlyArray<{ entity: string; actions: ReadonlyArray<Msg>; hidden: ReadonlyArray<string>; readOnly: ReadonlyArray<string> }> };
export type FlowStepRow = { n: number; from: string; to: string; action: string; who: string; rules: ReadonlyArray<Msg>; approval?: Msg };
export type FlowNode = { id: string; label: string; kind: 'initial' | 'normal' | 'final'; locked: boolean; col: number; row: number };
export type FlowEdge = { n: number; from: string; to: string; back: boolean };
export type FlowModel = { id: string; label: string; entity: string; nodes: ReadonlyArray<FlowNode>; edges: ReadonlyArray<FlowEdge>; steps: ReadonlyArray<FlowStepRow>; cols: number; rows: number };
export type PendingGroup = { cls: 'cosmetic' | 'process' | 'access' | 'money'; count: number; items: ReadonlyArray<Msg> };

export type Section =
  | { id: 'profile'; badges: Badges; facts: ReadonlyArray<{ label: Msg; value: Msg | string; ltr?: boolean }> }
  | { id: 'places'; badges: Badges; locations: ReadonlyArray<{ id: string; label: string; kind: Msg; city?: string }>; departments: ReadonlyArray<{ id: string; label: Msg }> }
  | { id: 'roles'; badges: Badges; roles: ReadonlyArray<RoleRow> }
  | { id: 'flows'; badges: Badges; flows: ReadonlyArray<FlowModel> }
  | { id: 'items'; badges: Badges; entities: ReadonlyArray<{ id: string; label: string; fields: ReadonlyArray<{ id: string; label: string; type: Msg; required: boolean }> }> }
  | { id: 'numbering'; badges: Badges; rows: ReadonlyArray<{ entity: string; sample: string; reset: Msg }> }
  | { id: 'settings'; badges: Badges; facts: ReadonlyArray<{ label: Msg; value: Msg | string; ltr?: boolean }> }
  | { id: 'assistants'; badges: Badges; assistants: ReadonlyArray<{ id: string; label: string; department: Msg; roles: ReadonlyArray<string>; tools: ReadonlyArray<{ text: Msg; confirm: boolean }>; limits: Msg; memory: Msg }> }
  | { id: 'pending'; badges: Badges; total: number; groups: ReadonlyArray<PendingGroup> };

export type SectionId = Section['id'];
export type BlueprintView = { scope: 'all' | 'department'; revision: number; buildState: string; badges: Badges; sections: ReadonlyArray<Section> };
