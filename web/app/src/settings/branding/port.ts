/**
 * Branding settings port (WEB-007). The screen talks only to this interface; the real adapter calls the
 * gateway (tenant settings tool) once it exists. Server side must re-check the caller's permission and
 * re-run the colour derivation (never trust the client's derived values).
 *
 * LOGO: the upload sanitiser, malware scan and per-tenant storage are SEC-006 (rules in SEC-018), NOT
 * built. So this port takes only a descriptor of a raster file, the screen never reads, renders or
 * previews the file's content, and SVG is refused here. The real adapter hands the bytes to the
 * SEC-006 pipeline; the logo is only usable after that pipeline reports it clean.
 */
import { DEFAULT_PRIMARY } from './colour';

export type BrandingSettings = { primary: string; logo: { assetId: string; fileName: string; status: 'pending_scan' | 'clean' } | null };
export type LogoCandidate = { fileName: string; mediaType: string; sizeBytes: number };
export type LogoResult = { ok: true; logo: NonNullable<BrandingSettings['logo']> } | { ok: false; code: 'type' | 'size' | 'failed' };
export type SaveResult = { ok: true } | { ok: false; code: 'forbidden' | 'invalid' | 'failed' };

export interface BrandingPort {
  load(): Promise<BrandingSettings>;
  save(settings: BrandingSettings): Promise<SaveResult>;
  uploadLogo(file: LogoCandidate): Promise<LogoResult>;
}

/** SEC-018 starting limits are enforced again by SEC-006; this only avoids a pointless round trip. */
export const LOGO_TYPES: ReadonlyArray<string> = ['image/png', 'image/jpeg'];
export const LOGO_MAX_BYTES = 2 * 1024 * 1024;

export function checkLogo(f: LogoCandidate): 'type' | 'size' | null {
  if (!LOGO_TYPES.includes(f.mediaType)) return 'type';
  return f.sizeBytes <= 0 || f.sizeBytes > LOGO_MAX_BYTES ? 'size' : null;
}

/** In-memory fake for tests and the fixture screen. Nothing leaves the browser. */
export function createFakeBrandingPort(initial: BrandingSettings = { primary: DEFAULT_PRIMARY, logo: null }, opts: { failSave?: boolean } = {}): BrandingPort & { saved: BrandingSettings[] } {
  let current = initial;
  const saved: BrandingSettings[] = [];
  return {
    saved,
    load: async () => current,
    save: async (s) => {
      if (opts.failSave) return { ok: false, code: 'failed' };
      current = s;
      saved.push(s);
      return { ok: true };
    },
    uploadLogo: async (f) => {
      const bad = checkLogo(f);
      return bad ? { ok: false, code: bad } : { ok: true, logo: { assetId: `fake-asset-${f.sizeBytes}`, fileName: f.fileName, status: 'pending_scan' } };
    },
  };
}
