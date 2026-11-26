/**
 * Editor state for the document templates screen (WEB-009), outside React so the stale-result rules are testable
 * without a DOM (same pattern as the branding controller). One controller belongs to one tenant; `attach()`'s
 * cleanup makes every late result a no-op. Until `load()` succeeds nothing is editable.
 */
import { DEFAULT_TEMPLATES, checkTemplate, TEMPLATE_KINDS, type DocumentTemplatesPort, type DocumentTemplatesSettings, type TemplateKind, type TemplateSettings } from './port';

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
    edit(kind: TemplateKind, patch: Partial<TemplateSettings>) {
      if (editable()) set({ settings: { ...state.settings, [kind]: { ...state.settings[kind], ...patch } }, status: 'idle' });
    },
    /** True when every template passes the same check the server runs. */
    valid: () => TEMPLATE_KINDS.every((k) => checkTemplate(state.settings[k])),
    async save() {
      if (!editable() || !TEMPLATE_KINDS.every((k) => checkTemplate(state.settings[k]))) return;
      const mine = generation;
      set({ status: 'saving' });
      const r = await port.save(state.settings);
      if (attached && mine === generation) set({ status: r.ok ? 'saved' : r.code });
    },
  };
}
export type DocumentTemplatesController = ReturnType<typeof createDocumentTemplatesController>;
