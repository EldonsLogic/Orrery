// WEB-029: apply the saved theme and language before first paint. The static export prerenders Arabic and the default
// theme; this blocking inline script (in <head>) sets data-theme, lang and dir from localStorage at once, and marks
// <html> with `locale-pending` when the saved language differs from the prerendered text so CSS hides the body until
// the provider has switched locale. Pure text builder: the root layout inlines it; tests run it against fakes.
import { bootScript, storageKey } from '../../theme/theme-engine.js';
import { defaultLocale, directionOf, locales } from '../i18n';

export const LOCALE_STORAGE_KEY = 'platform.locale.v1';
export const PENDING_CLASS = 'locale-pending';
export const PENDING_TIMEOUT_MS = 1500;
// Synthetic fixture ids; real ids come from identity (ADR-0007) later.
export const THEME_FIXTURE = { tenantId: 'tenant-fixture-synthetic', userId: 'user-fixture-synthetic' };

export function firstPaintScript(): string {
  const dirs = Object.fromEntries(locales.map((l) => [l, directionOf(l)]));
  const themePart = bootScript(storageKey(THEME_FIXTURE.tenantId, THEME_FIXTURE.userId));
  const localePart =
    `(function(){try{var d=document.documentElement,D=${JSON.stringify(dirs)},` +
    `l=localStorage.getItem(${JSON.stringify(LOCALE_STORAGE_KEY)});` +
    `if(l&&Object.prototype.hasOwnProperty.call(D,l)){d.lang=l;d.dir=D[l];` +
    `if(l!==${JSON.stringify(defaultLocale)}){d.classList.add(${JSON.stringify(PENDING_CLASS)});` +
    `setTimeout(function(){d.classList.remove(${JSON.stringify(PENDING_CLASS)})},${PENDING_TIMEOUT_MS})}}}catch(e){}})();`;
  return themePart + localePart;
}

// Called by the provider once the saved locale is rendered (and by its own safety timeout).
export function releaseLocalePending(root: { classList: { remove(c: string): void } }): void {
  root.classList.remove(PENDING_CLASS);
}
