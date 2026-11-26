/**
 * Document templates settings port (WEB-009). The screen talks only to this interface; the real adapter
 * calls the gateway (tenant settings tool) once it exists, and the server re-validates everything here.
 *
 * What a tenant may change per template: logo placement, an accent chosen from the tenant's token set
 * (a token NAME, never a colour value) and a footer text. Nothing else. The compliance layout
 * (LOCKED_REGIONS, mirrored from the engine's locked document kinds, ERP-016) is shown read-only and has
 * no field in these types, so the UI cannot send an edit for it.
 *
 * UNVERIFIED / follow-up (partner lane, ERP-016): the engine's branding input today takes display name,
 * primary, accent, logo, mono-logo and the powered-by flag. It has no per-template logo placement or footer
 * text yet, so the real adapter needs that contract before this screen can be wired live.
 */
import { plainText } from '../../factory/text';

export const TEMPLATE_KINDS = ['tax_invoice', 'quote', 'purchase_order'] as const;
export type TemplateKind = (typeof TEMPLATE_KINDS)[number];
/** Logical positions in the header: start is the left in English and the right in Arabic. */
export const LOGO_PLACEMENTS = ['start', 'center', 'end'] as const;
export type LogoPlacement = (typeof LOGO_PLACEMENTS)[number];
/** Token names from the tenant theme (--color-primary, --color-accent). */
export const ACCENT_TOKENS = ['primary', 'accent'] as const;
export type AccentToken = (typeof ACCENT_TOKENS)[number];
export const FOOTER_MAX = 200;

export type TemplateSettings = { logoPlacement: LogoPlacement; accent: AccentToken; footerText: string };
export type DocumentTemplatesSettings = Record<TemplateKind, TemplateSettings>;
export type SaveResult = { ok: true } | { ok: false; code: 'forbidden' | 'invalid' | 'failed' };

export interface DocumentTemplatesPort {
  load(): Promise<DocumentTemplatesSettings>;
  save(settings: DocumentTemplatesSettings): Promise<SaveResult>;
}

/** Region names in document order, from the engine's locked document kinds (document_layout.py). */
export const LOCKED_REGIONS: Record<TemplateKind, ReadonlyArray<string>> = {
  tax_invoice: ['header', 'seller', 'buyer', 'lines', 'totals', 'qr'],
  quote: ['header', 'seller', 'buyer', 'lines', 'totals', 'terms'],
  purchase_order: ['header', 'buyer', 'supplier', 'delivery', 'lines', 'totals', 'terms'],
};

const base: TemplateSettings = { logoPlacement: 'start', accent: 'primary', footerText: '' };
export const DEFAULT_TEMPLATES: DocumentTemplatesSettings = { tax_invoice: { ...base }, quote: { ...base }, purchase_order: { ...base } };

/** Same rule the server applies: known tokens only, footer is plain text (no control or bidi characters) within the limit. */
export function checkTemplate(t: TemplateSettings): boolean {
  return (
    (LOGO_PLACEMENTS as ReadonlyArray<string>).includes(t.logoPlacement) &&
    (ACCENT_TOKENS as ReadonlyArray<string>).includes(t.accent) &&
    typeof t.footerText === 'string' &&
    t.footerText.length <= FOOTER_MAX &&
    plainText(t.footerText, FOOTER_MAX) === t.footerText
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
      if (!TEMPLATE_KINDS.every((k) => s[k] && checkTemplate(s[k]))) return { ok: false, code: 'invalid' };
      current = s;
      saved.push(s);
      return { ok: true };
    },
  };
}
