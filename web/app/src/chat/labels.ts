// Customer-facing words for what the chat shows (WEB-029). Tool ids and risk codes are internal: the screen shows an action
// in words ("Update sales order") and the Blueprint's own labels for fields and states, in the reader's language. Pure.
import { pick } from '../records/labels';
import type { RecordsData } from '../records/types';
import type { ChangeLine } from './types';

/** Verbs with a translated phrase under chat.tools; any other tool reads as the generic phrase. */
export const TOOL_VERBS = ['list', 'get', 'create', 'update', 'submit', 'cancel', 'deliver'] as const;
export type ToolVerb = (typeof TOOL_VERBS)[number];

const TOOL = /^([a-z][a-z0-9_]{0,47})\.([a-z][a-z0-9_]{0,47})$/;

export type ToolPhrase = { key: ToolVerb | 'generic'; entity: string };

/** The phrase key and the entity name for a tool id. Unknown tools or entities never fall back to the raw id. */
export function toolPhrase(data: RecordsData, tool: string, locale: string): ToolPhrase {
  const m = TOOL.exec(tool);
  const def = m ? data.entities.find((e) => e.id === m[1]) : undefined;
  const verb = m?.[2] as ToolVerb | undefined;
  if (!def || !verb || !TOOL_VERBS.includes(verb)) return { key: 'generic', entity: '' };
  const name = verb === 'list' ? pick(def.pluralLabels, locale, def.id) : pick(def.labels, locale, def.id);
  // Mid-sentence in English the entity is lower case ("Update sales order"); Arabic has no case.
  return { key: verb, entity: locale === 'en' ? name.toLowerCase() : name };
}

export type ChangeView = { label: string; before: string; after: string };

/**
 * A change line in the reader's language: the field label from the Blueprint (or the status word for `state`), workflow
 * state values from their labels. Dates and amounts stay as they are (one digit system). Without a known field the
 * server's own label is used.
 */
export function changeView(data: RecordsData, entityId: string | undefined, c: ChangeLine, locale: string, statusWord: string): ChangeView {
  const entity = entityId ? data.entities.find((e) => e.id === entityId) : undefined;
  if (entity && c.field === 'state') {
    const wf = data.workflows.find((w) => w.id === entity.workflow);
    const state = (id: string) => {
      const s = wf?.states.find((x) => x.id === id);
      return s ? pick(s.labels, locale, id) : id;
    };
    return { label: statusWord, before: c.before && state(c.before), after: c.after && state(c.after) };
  }
  const field = entity && c.field ? entity.fields.find((f) => f.id === c.field) : undefined;
  if (!field) return { label: c.label, before: c.before, after: c.after };
  const option = (v: string) => {
    const o = field.options?.find((x) => x.value === v);
    return o ? pick(o.labels, locale, v) : v;
  };
  return { label: pick(field.labels, locale, field.id), before: option(c.before), after: option(c.after) };
}
