// Deny by default: a tool the set does not contain, or the caller's roles do not allow, yields nothing.
import type { Caller, ToolDef } from './types';

export const toolFor = (tools: ReadonlyArray<ToolDef>, entity: string, verb: string): ToolDef | undefined =>
  tools.find((t) => t.name === `${entity}.${verb}` && t.entity === entity);

export const roleAllows = (roles: ReadonlyArray<string>, caller: Caller): boolean =>
  roles.some((r) => caller.roleIds.includes(r));

/** The tool exists in the set and at least one of the caller's roles may call it. */
export const usable = (tool: ToolDef | undefined, caller: Caller): tool is ToolDef =>
  tool !== undefined && roleAllows(tool.requires.roles, caller);

const listed = (m: Readonly<Record<string, ReadonlyArray<string>>> | undefined, caller: Caller): Set<string> =>
  new Set(caller.roleIds.flatMap((r) => m?.[r] ?? []));

/** Fail closed with several roles: hidden or read-only for any of the caller's roles means hidden or read-only. */
export const hiddenFields = (tools: ReadonlyArray<ToolDef | undefined>, caller: Caller): Set<string> =>
  new Set(tools.flatMap((t) => [...listed(t?.field_access?.hidden_by_role, caller)]));

export const readOnlyFields = (tools: ReadonlyArray<ToolDef | undefined>, caller: Caller): Set<string> =>
  new Set(tools.flatMap((t) => [...listed(t?.field_access?.read_only_by_role, caller)]));
