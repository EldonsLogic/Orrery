// DSC-007: Blueprint JSON to owner-readable sections. Pure functions, no browser, no network.
// Output holds i18n keys (relative to the `blueprint` message namespace) and data values; the
// component turns them into words. Nothing here names the engine, a component or a tool API.
import { scopeOf } from './access';
import { layoutFlow } from './flows';
import { dayName, joinList, languageName, monthDay, numberText, pick, regionName } from './format';
import { summarisePending } from './pending';
import {
  msg,
  type Badges,
  type Blueprint,
  type BlueprintView,
  type BpEntity,
  type BpGuard,
  type BpRole,
  type BpWorkflow,
  type Caller,
  type DiffOp,
  type FlowModel,
  type Msg,
  type RoleRow,
  type Section,
} from './types';

const yesNo = (v: boolean | undefined): Msg => msg(v ? 'yes' : 'no');

export function buildBlueprintView(bp: Blueprint, caller: Caller, locale: string, pending: ReadonlyArray<DiffOp> = []): BlueprintView {
  const scope = scopeOf(bp, caller);
  const draft = bp.meta.buildState === 'draft';
  const plain: Badges = { draft, unverified: false };
  // The tax and calendar settings come from a country pack still below 1.0.0: show them as unverified.
  const unverified: Badges = { draft, unverified: (bp.compliance.countryPack?.version ?? '0').startsWith('0.') };
  if (scope.roles.length === 0) return { scope: 'department', revision: bp.meta.revision, buildState: bp.meta.buildState, badges: plain, sections: [] }; // deny by default

  const ent = (id: string) => bp.entities.find((e) => e.id === id);
  const entLabel = (id: string) => pick(ent(id)?.labels, locale, id);
  const roleLabel = (id: string) => pick(bp.roles.find((r) => r.id === id)?.labels, locale, id);
  const roleList = (ids: ReadonlyArray<string>) => joinList(ids.map(roleLabel), locale);
  const inScope = (e: BpEntity) => scope.all || scope.entities.has(e.id);
  const sys = bp.company.locale.numberSystem;
  const fieldLabel = (entity: string, field: string) => pick(ent(entity)?.fields.find((f) => f.id === field)?.labels, locale, field);
  const guardMsg = (entity: string, g: BpGuard): Msg =>
    msg(`guard.${g.op}`, {
      field: fieldLabel(entity, g.field),
      value: `${numberText(g.value, locale, sys)}${ent(entity)?.fields.find((f) => f.id === g.field)?.type === 'money' ? ` ${bp.company.locale.currency}` : ''}`,
    });

  const sections: Section[] = [];

  if (scope.all) {
    const c = bp.company;
    const names = [pick(c.legalName, locale, ''), pick(c.tradeName, locale, '')].filter((n, i, a) => n && a.indexOf(n) === i);
    sections.push({
      id: 'profile',
      badges: plain,
      facts: [
        { label: msg('profile.name'), value: names.join(' / ') },
        { label: msg('profile.country'), value: regionName(c.country, locale) },
        ...(c.crNumber ? [{ label: msg('profile.cr'), value: c.crNumber, ltr: true }] : []),
        ...(c.vatNumber ? [{ label: msg('profile.vat'), value: c.vatNumber, ltr: true }] : []),
        ...(c.sizeBand ? [{ label: msg('profile.size'), value: msg('profile.sizeValue', { band: c.sizeBand }) }] : []),
        { label: msg('profile.languages'), value: joinList([c.languages.primary, ...(c.languages.secondary ?? [])].map((l) => languageName(l, locale)), locale) },
      ],
    });
  }

  const locations = bp.locations.filter((l) => scope.all || scope.locations.has(l.id));
  const functions = [...new Set(scope.roles.map((r) => r.function))];
  const depFns = scope.all ? [...new Set(bp.roles.map((r) => r.function))] : functions;
  if (locations.length > 0 || depFns.length > 0) {
    sections.push({
      id: 'places',
      badges: plain,
      locations: locations.map((l) => ({ id: l.id, label: pick(l.labels, locale, l.id), kind: msg(`locationKind.${l.kind}`), city: l.city })),
      departments: depFns.map((f) => ({ id: f, label: msg(`function.${f}`) })),
    });
  }

  const rolesShown: ReadonlyArray<BpRole> = scope.all ? bp.roles : scope.roles;
  const roleRows: RoleRow[] = rolesShown.map((r) => ({
    id: r.id,
    label: pick(r.labels, locale, r.id),
    scope: msg(`scope.${r.scope.type}`, { places: joinList((r.scope.values ?? []).map((v) => pick(bp.locations.find((l) => l.id === v)?.labels, locale, v)), locale) }),
    rules: (r.permissions ?? []).map((p) => ({
      entity: entLabel(p.entity),
      actions: p.actions.map((a) => msg(`action.${a}`)),
      hidden: (p.hiddenFields ?? []).map((f) => fieldLabel(p.entity, f)),
      readOnly: (p.readOnlyFields ?? []).map((f) => fieldLabel(p.entity, f)),
    })),
  }));
  sections.push({ id: 'roles', badges: plain, roles: roleRows });

  const flowOf = (wf: BpWorkflow): FlowModel => {
    const layout = layoutFlow(wf, (l, id) => pick(l, locale, id));
    const stateLabel = (id: string) => layout.nodes.find((n) => n.id === id)?.label ?? id;
    return {
      id: wf.id,
      label: pick(wf.labels, locale, wf.id),
      entity: entLabel(wf.entity),
      ...layout,
      steps: wf.transitions.map((t, i) => {
        const ap = t.approval ? bp.approvals?.find((a) => a.id === t.approval) : undefined;
        return {
          n: i + 1,
          from: stateLabel(t.from),
          to: stateLabel(t.to),
          action: pick(t.actionLabels, locale, t.id),
          who: roleList(t.allowedRoles),
          rules: (t.guards ?? []).map((g) => guardMsg(wf.entity, g)),
          approval: ap ? msg('flow.approval', { name: pick(ap.labels, locale, ap.id), approver: roleList(ap.steps.map((s) => s.approverRole)) }) : undefined,
        };
      }),
    };
  };
  const flows = (bp.workflows ?? []).filter((w) => scope.all || scope.entities.has(w.entity)).map(flowOf);
  if (flows.length > 0) sections.push({ id: 'flows', badges: plain, flows });

  const hiddenFor = (entity: string) => new Set(scope.roles.flatMap((r) => r.permissions?.find((p) => p.entity === entity)?.hiddenFields ?? []));
  const masters = bp.entities.filter((e) => e.kind === 'master' && inScope(e));
  if (masters.length > 0) {
    sections.push({
      id: 'items',
      badges: plain,
      entities: masters.map((e) => ({
        id: e.id,
        label: pick(e.pluralLabels, locale, e.id),
        fields: e.fields
          .filter((f) => scope.all || !hiddenFor(e.id).has(f.id))
          .map((f) => ({ id: f.id, label: pick(f.labels, locale, f.id), type: msg(`fieldType.${f.type}`), required: f.required === true })),
      })),
    });
  }

  const numbered = bp.entities.filter((e) => e.numbering && inScope(e));
  if (numbered.length > 0) {
    sections.push({
      id: 'numbering',
      badges: plain,
      rows: numbered.map((e) => ({
        entity: pick(e.labels, locale, e.id),
        sample: `${e.numbering?.prefix ?? ''}${String(1).padStart(e.numbering?.padding ?? 1, '0')}`,
        reset: msg(e.numbering?.resetPerFiscalYear ? 'numbering.reset' : 'numbering.keep'),
      })),
    });
  }

  if (scope.all) {
    const l = bp.company.locale;
    const v = bp.compliance.vat;
    const wt = l.workingTime;
    const hours = (h: { from: string; to: string }) => `${h.from}–${h.to}`;
    sections.push({
      id: 'settings',
      badges: unverified,
      facts: [
        { label: msg('settings.currency'), value: l.currency, ltr: true },
        { label: msg('settings.vatRegistered'), value: yesNo(v?.registered) },
        ...(v?.registered ? [
          { label: msg('settings.vatRate'), value: `${numberText(v.defaultRatePercent ?? 0, locale, sys)}%`, ltr: true },
          { label: msg('settings.vatFiling'), value: msg(`filing.${v.filingPeriod ?? 'quarterly'}`) },
          { label: msg('settings.vatInclusive'), value: yesNo(v.pricesIncludeVat) },
        ] : []),
        ...(bp.compliance.eInvoicing ? [{ label: msg('settings.einvoice'), value: msg(`einv.${bp.compliance.eInvoicing.mode}`, { stage: msg(`env.${bp.compliance.eInvoicing.environment ?? 'sandbox'}`) }) }] : []),
        { label: msg('settings.calendar'), value: msg(`calendar.${l.calendar.primary}`) },
        { label: msg('settings.calendarSecond'), value: msg(`calendar.${l.calendar.secondaryDisplay ?? 'none'}`) },
        { label: msg('settings.weekStart'), value: dayName(l.week.startDay, locale) },
        { label: msg('settings.weekend'), value: joinList(l.week.weekendDays.map((d) => dayName(d, locale)), locale) },
        ...(wt ? [
          { label: msg('settings.workDays'), value: joinList(wt.workDays.map((d) => dayName(d, locale)), locale) },
          { label: msg('settings.workHours'), value: hours(wt.hours), ltr: true },
          ...(wt.reducedPeriods ?? []).map((p) => ({ label: msg('settings.reduced', { name: pick(p.labels, locale, p.id) }), value: hours(p.hours), ltr: true })),
        ] : []),
        { label: msg('settings.fiscalYear'), value: msg('settings.fiscalFrom', { date: monthDay(l.fiscalYear.startMonth, l.fiscalYear.startDay, locale) }) },
        { label: msg('settings.holidays'), value: msg('settings.holidaysValue', { count: l.holidays?.overrides?.length ?? 0 }) },
        { label: msg('settings.timezone'), value: l.timezone, ltr: true },
        { label: msg('settings.digits'), value: msg(`digits.${l.numberSystem}`) },
      ],
    });
  }

  const toolMsg = (tool: string, steps?: ReadonlyArray<string>): Msg => {
    const [entity = '', verb = ''] = tool.split('.');
    const known = ['list', 'read', 'create', 'update', 'delete', 'transition'].includes(verb);
    if (!known) return msg('tool.other', { name: tool });
    const stepNames = (steps ?? []).map((id) => pick((bp.workflows ?? []).flatMap((w) => w.transitions).find((t) => t.id === id)?.actionLabels, locale, id));
    return msg(`tool.${verb === 'read' ? 'list' : verb}`, { entity: entLabel(entity), steps: joinList(stepNames, locale) });
  };
  const assistants = (bp.assistants ?? []).filter((a) => scope.all || a.roles.some((r) => caller.roleIds.includes(r)));
  if (assistants.length > 0) {
    sections.push({
      id: 'assistants',
      badges: plain,
      assistants: assistants.map((a) => ({
        id: a.id,
        label: pick(a.labels, locale, a.id),
        department: msg(`function.${a.department}`),
        roles: a.roles.map(roleLabel),
        tools: a.tools.map((t) => ({ text: toolMsg(t.tool, t.transitions), confirm: t.confirm === true })),
        limits: msg('assistants.limits', { calls: a.limits.perCall.maxToolCalls, rows: a.limits.perCall.maxRows, day: a.limits.perDay.maxToolCalls, writes: a.limits.perDay.maxWrites }),
        memory: msg(`memory.${a.memory.scope}`),
      })),
    });
  }

  if (scope.all) sections.push({ id: 'pending', badges: plain, ...summarisePending(pending, locale) });

  return { scope: scope.all ? 'all' : 'department', revision: bp.meta.revision, buildState: bp.meta.buildState, badges: plain, sections };
}
