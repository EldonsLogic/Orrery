'use client';

import { useEffect, useState } from 'react';
import { createThemeEngine } from '../../theme/theme-engine.js';

type Mode = 'light' | 'dark' | 'system';
type Engine = ReturnType<typeof createThemeEngine>;

// Synthetic fixture ids; real ids come from identity (ADR-0007) later.
const FIXTURE = { tenantId: 'tenant-fixture-synthetic', userId: 'user-fixture-synthetic' };

// Thin client hook over the merged theme engine (BRD-005).
export function useTheme(): { mode: Mode; setMode: (m: Mode) => void } {
  const [mode, setModeState] = useState<Mode>('system');
  const [engine, setEngine] = useState<Engine | null>(null);

  useEffect(() => {
    const e = createThemeEngine({
      root: document.documentElement,
      storage: window.localStorage,
      matchMedia: window.matchMedia.bind(window),
      ...FIXTURE,
    });
    setEngine(e);
    setModeState(e.get().mode as Mode);
    const off = e.subscribe((s: { mode: Mode }) => setModeState(s.mode));
    return () => {
      off();
      e.destroy();
    };
  }, []);

  return { mode, setMode: (m) => engine?.set(m) };
}
