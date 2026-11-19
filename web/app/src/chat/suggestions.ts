/** Suggested prompts per role (the role view-model). Keys live under chat.suggestions; deny by default: unknown roles get the generic set. */
const BY_ROLE: Readonly<Record<string, ReadonlyArray<string>>> = {
  owner: ['owner.cash', 'owner.approvals', 'owner.sales'],
  general_manager: ['owner.cash', 'owner.approvals', 'owner.sales'],
  accountant: ['accountant.overdue', 'accountant.vat', 'accountant.draft'],
  sales_rep: ['sales.open', 'sales.quote', 'sales.customer'],
};
const GENERIC = ['generic.what', 'generic.help', 'generic.recent'];

export function suggestionKeys(roles: ReadonlyArray<string>): ReadonlyArray<string> {
  for (const r of roles) if (BY_ROLE[r]) return BY_ROLE[r];
  return GENERIC;
}
