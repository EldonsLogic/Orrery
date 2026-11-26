/**
 * Editor state for the branding screen (WEB-007), kept outside React so the stale-result rules are testable
 * without a DOM. One controller belongs to one tenant: the screen creates a new one (and a new port) when the
 * active workspace changes, and `attach()`'s cleanup makes every late result of the old one a no-op.
 * Until `load()` succeeds nothing is editable, so a late load can never overwrite an edit.
 */
import { DEFAULT_PRIMARY } from './colour';
import { checkLogo, type BrandingPort, type BrandingSettings, type LogoCandidate } from './port';

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'forbidden' | 'invalid' | 'failed';
export type LogoError = 'errType' | 'errSize' | 'errFailed';
export type BrandingState = {
  text: string;
  logo: BrandingSettings['logo'];
  logoError: LogoError | null;
  status: SaveStatus;
  loaded: 'loading' | 'ready' | 'failed';
};

export function createBrandingController(port: BrandingPort, initial: BrandingSettings | null) {
  let state: BrandingState = { text: initial?.primary ?? DEFAULT_PRIMARY, logo: initial?.logo ?? null, logoError: null, status: 'idle', loaded: initial ? 'ready' : 'loading' };
  const subs = new Set<() => void>();
  let attached = false;
  let generation = 0;
  const set = (patch: Partial<BrandingState>) => {
    state = { ...state, ...patch };
    subs.forEach((f) => f());
  };
  const editable = () => state.loaded === 'ready';

  const load = () => {
    if (initial) return;
    const mine = ++generation;
    set({ loaded: 'loading' });
    void port.load().then(
      (s) => attached && mine === generation && set({ text: s.primary, logo: s.logo, loaded: 'ready' }),
      () => attached && mine === generation && set({ loaded: 'failed' }),
    );
  };

  return {
    get: () => state,
    subscribe: (f: () => void) => {
      subs.add(f);
      return () => void subs.delete(f);
    },
    /** Starts loading; the returned cleanup (unmount or tenant change) drops every result still in flight. */
    attach: () => {
      attached = true;
      if (state.loaded === 'loading') load();
      return () => {
        attached = false;
        generation++;
      };
    },
    setText: (text: string) => editable() && set({ text }),
    async save(primary: string) {
      if (!editable()) return;
      const mine = generation;
      set({ status: 'saving' });
      const r = await port.save({ primary, logo: state.logo });
      if (attached && mine === generation) set({ status: r.ok ? 'saved' : r.code });
    },
    // Only the file's name, type and size are read; its bytes are never opened (SEC-006 not built).
    async uploadLogo(file: LogoCandidate) {
      if (!editable()) return;
      set({ logoError: null });
      const bad = checkLogo(file);
      if (bad) return set({ logoError: bad === 'type' ? 'errType' : 'errSize' });
      const mine = generation;
      const r = await port.uploadLogo(file);
      if (!attached || mine !== generation) return;
      if (r.ok) set({ logo: r.logo });
      else set({ logoError: r.code === 'type' ? 'errType' : r.code === 'size' ? 'errSize' : 'errFailed' });
    },
  };
}
export type BrandingController = ReturnType<typeof createBrandingController>;
