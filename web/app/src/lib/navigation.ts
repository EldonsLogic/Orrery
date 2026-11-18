// Role-aware navigation view-model (WEB-003). Pure: Blueprint data and the caller in, items out.
// Deny by default through the same check the record screens use: an entity appears only when its
// list tool exists in the generated set and one of the caller's roles may call it.
import { pick } from '../records/labels';
import { toolFor, usable } from '../records/access';
import type { Caller, RecordsData } from '../records/types';

export type NavItem = { id: string; label: string; href: string };
export type NavSection = { id: 'workspace' | 'records'; items: ReadonlyArray<NavItem> };

export function buildNav(data: RecordsData, caller: Caller, locale: string, labels: { home: string }): NavSection[] {
  const records = data.entities
    .filter((e) => usable(toolFor(data.tools, e.id, 'list'), caller))
    .map((e) => ({ id: e.id, label: pick(e.pluralLabels, locale, e.id), href: `/records/${e.id}/` }));
  const sections: NavSection[] = [{ id: 'workspace', items: [{ id: 'home', label: labels.home, href: '/home/' }] }];
  if (records.length > 0) sections.push({ id: 'records', items: records });
  return sections;
}
