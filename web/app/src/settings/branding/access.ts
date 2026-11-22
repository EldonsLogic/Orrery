// Deny by default, same rule as the Blueprint viewer: only owner and general manager (roles the tenant's Blueprint
// defines) may change branding. The gateway enforces this again; the screen check only hides what would be refused.
import { scopeOf } from '../../blueprint/access';
import type { Blueprint, Caller } from '../../blueprint/types';

export const canEditBranding = (bp: Blueprint, caller: Caller): boolean => scopeOf(bp, caller).all;
