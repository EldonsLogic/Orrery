/**
 * Document templates settings port (WEB-009). The screen talks only to this interface; the real adapter
 * calls the gateway (tenant settings tool) once it exists, and the server re-validates everything here.
 *
 * The settings mirror the Blueprint contract `branding.documentHeader` (contracts/blueprint.schema.json):
 * tenant-wide, not per template. A tenant may change the logo position (logical start/center/end, flips in RTL),
 * whether the primary colour marks table headers (`accentOnDocuments`, a boolean, never a colour value) and a
 * bilingual footer text ({ar, en}). Nothing else. The compliance layout (LOCKED_REGIONS, mirrored from the
 * engine's locked document kinds, ERP-016) is shown read-only and has no field in these types. The footer
 * is a locked region on every kind (document reference and the entitlement-gated mark); the tenant text is a
 * smaller slot inside it.
 */
import { plainText } from '../../factory/text';

/** Document kinds shown in the preview. The settings apply to all of them. */
export const TEMPLATE_KINDS = ['tax_invoice', 'quote', 'purchase_order'] as const;
export type TemplateKind = (typeof TEMPLATE_KINDS)[number];
/** Logical positions in the header: start is the left in English and the right in Arabic (contract logoPosition). */
export const LOGO_PLACEMENTS = ['start', 'center', 'end'] as const;
export type LogoPlacement = (typeof LOGO_PLACEMENTS)[number];
export const FOOTER_MAX = 200;
export const FOOTER_LOCALES = ['ar', 'en'] as const;
export type FooterText = { ar: string; en: string };

export type DocumentTemplatesSettings = { logoPosition: LogoPlacement; accentOnDocuments: boolean; footerText: FooterText };
export type SaveResult = { ok: true } | { ok: false; code: 'forbidden' | 'invalid' | 'failed' };

export interface DocumentTemplatesPort {
  load(): Promise<DocumentTemplatesSettings>;
  save(settings: DocumentTemplatesSettings): Promise<SaveResult>;
}

/** Region names in document order, from the engine's locked document kinds (document_layout.py). The footer is locked and last. */
export const LOCKED_REGIONS: Record<TemplateKind, ReadonlyArray<string>> = {
  tax_invoice: ['header', 'seller', 'buyer', 'lines', 'totals', 'qr', 'footer'],
  quote: ['header', 'seller', 'buyer', 'lines', 'totals', 'terms', 'footer'],
  purchase_order: ['header', 'buyer', 'supplier', 'delivery', 'lines', 'totals', 'terms', 'footer'],
};

export const DEFAULT_TEMPLATES: DocumentTemplatesSettings = { logoPosition: 'start', accentOnDocuments: false, footerText: { ar: '', en: '' } };

/** Per-locale footer check: plain text (no control or bidi characters) within the limit. */
export const footerLocaleOk = (v: unknown): boolean => typeof v === 'string' && v.length <= FOOTER_MAX && plainText(v, FOOTER_MAX) === v;

/**
 * Same rule the server applies: known position, boolean accent flag, and a footer that is either empty in both
 * languages (no footer text) or filled in both (the contract's localizedText needs ar and en), each plain text.
 */
export function checkTemplate(t: DocumentTemplatesSettings): boolean {
  const f = t?.footerText;
  if (!f || typeof f !== 'object') return false;
  const filled = FOOTER_LOCALES.filter((l) => typeof f[l] === 'string' && f[l] !== '').length;
  return (
    (LOGO_PLACEMENTS as ReadonlyArray<string>).includes(t.logoPosition) &&
    typeof t.accentOnDocuments === 'boolean' &&
    FOOTER_LOCALES.every((l) => footerLocaleOk(f[l])) &&
    (filled === 0 || filled === FOOTER_LOCALES.length)
  );
}

/** In-memory fake for tests and the fixture screen. Nothing leaves the browser. */
export function createFakeDocumentTemplatesPort(initial: DocumentTemplatesSettings = DEFAULT_TEMPLATES): DocumentTemplatesPort & { saved: DocumentTemplatesSettings[] } {
  let current = initial;
  const saved: DocumentTemplatesSettings[] = [];
  return {
    saved,
    load: async () => current,
    save: async (s) => {
      if (!checkTemplate(s)) return { ok: false, code: 'invalid' };
      current = s;
      saved.push(s);
      return { ok: true };
    },
  };
}
