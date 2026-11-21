'use client';

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { NextIntlClientProvider } from 'next-intl';
import { RouteTitle } from './RouteTitle';
import { defaultLocale, directionOf, isLocale, messages, type Direction, type Locale } from '../i18n';

const STORAGE_KEY = 'platform.locale.v1'; // the user's language setting (fixture until settings exist)

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
  const direction = override ?? directionOf(locale);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (isLocale(stored)) setLocaleState(stored);
    } catch {
      /* storage unavailable: keep default */
    }
  }, []);

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
