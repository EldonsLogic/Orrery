'use client';

import { useEffect, useState } from 'react';
import { createThemeEngine } from '../../theme/theme-engine.js';
import { THEME_FIXTURE as FIXTURE } from './firstPaint';

type Mode = 'light' | 'dark' | 'system';
type Engine = ReturnType<typeof createThemeEngine>;


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
