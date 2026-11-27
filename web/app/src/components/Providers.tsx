'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { NextIntlClientProvider } from 'next-intl';
import { RouteTitle } from './RouteTitle';
import { LOCALE_STORAGE_KEY, PENDING_TIMEOUT_MS, releaseLocalePending } from '../lib/firstPaint';
import { defaultLocale, directionOf, isLocale, messages, type Direction, type Locale } from '../i18n';

const STORAGE_KEY = LOCALE_STORAGE_KEY; // the user's language setting (fixture until settings exist); shared with the first-paint script

type Settings = { locale: Locale; setLocale: (l: Locale) => void; direction: Direction; setDirection: (d: Direction | null) => void };
const SettingsContext = createContext<Settings | null>(null);

export function useSettings(): Settings {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings outside Providers');
  return ctx;
}

export function Providers({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(defaultLocale);
  const [override, setOverride] = useState<Direction | null>(null);
  const [restored, setRestored] = useState(false); // the saved locale has been read and applied
  const direction = override ?? directionOf(locale);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (isLocale(stored)) setLocaleState(stored);
    } catch {
      /* storage unavailable: keep default */
    }
    setRestored(true);
    // Safety net: the first-paint script hides the body while the saved locale differs; never leave it hidden.
    const t = setTimeout(() => releaseLocalePending(document.documentElement), PENDING_TIMEOUT_MS);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (restored) releaseLocalePending(document.documentElement);
  }, [restored, locale]);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = direction;
  }, [locale, direction]);

  const setLocale = (l: Locale) => {
    setLocaleState(l);
    setOverride(null);
    try {
      window.localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* ignore */
    }
  };

  return (
    <SettingsContext.Provider value={{ locale, setLocale, direction, setDirection: setOverride }}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone="UTC">
        <RouteTitle />
        {children}
      </NextIntlClientProvider>
    </SettingsContext.Provider>
  );
}
