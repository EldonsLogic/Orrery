/**
 * Editor state for the document templates screen (WEB-009), outside React so the stale-result rules are testable
 * without a DOM (same pattern as the branding controller). One controller belongs to one tenant; `attach()`'s
 * cleanup makes every late result a no-op. Until `load()` succeeds nothing is editable.
 */
import { DEFAULT_TEMPLATES, checkTemplate, type DocumentTemplatesPort, type DocumentTemplatesSettings } from './port';

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'forbidden' | 'invalid' | 'failed';
export type DocumentTemplatesState = {
  settings: DocumentTemplatesSettings;
  status: SaveStatus;
  loaded: 'loading' | 'ready' | 'failed';
};

export function createDocumentTemplatesController(port: DocumentTemplatesPort, initial: DocumentTemplatesSettings | null) {
  let state: DocumentTemplatesState = { settings: initial ?? DEFAULT_TEMPLATES, status: 'idle', loaded: initial ? 'ready' : 'loading' };
  const subs = new Set<() => void>();
  let attached = false;
  let generation = 0;
  const set = (patch: Partial<DocumentTemplatesState>) => {
    state = { ...state, ...patch };
    subs.forEach((f) => f());
  };
  const editable = () => state.loaded === 'ready';

  return {
    get: () => state,
    subscribe: (f: () => void) => {
      subs.add(f);
      return () => void subs.delete(f);
    },
    attach: () => {
      attached = true;
      if (state.loaded === 'loading') {
        const mine = ++generation;
        void port.load().then(
          (s) => attached && mine === generation && set({ settings: s, loaded: 'ready' }),
          () => attached && mine === generation && set({ loaded: 'failed' }),
        );
      }
      return () => {
        attached = false;
        generation++;
      };
    },
    edit(patch: Partial<DocumentTemplatesSettings>) {
      if (editable()) set({ settings: { ...state.settings, ...patch }, status: 'idle' });
    },
    /** True when the settings pass the same check the server runs. */
    valid: () => checkTemplate(state.settings),
    async save() {
      if (!editable() || !checkTemplate(state.settings)) return;
      const mine = generation;
      set({ status: 'saving' });
      const r = await port.save(state.settings);
      if (attached && mine === generation) set({ status: r.ok ? 'saved' : r.code });
    },
  };
}
export type DocumentTemplatesController = ReturnType<typeof createDocumentTemplatesController>;
