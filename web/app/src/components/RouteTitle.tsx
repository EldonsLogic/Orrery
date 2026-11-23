'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';

const ROUTES = ['home', 'chat', 'blueprint', 'onboarding', 'records', 'console', 'login', 'reset-password'] as const;

/** Sets a per-route document title in the active language (WCAG 2.4.2). Unknown routes keep the default title. */
export function RouteTitle() {
  const t = useTranslations('pwa');
  const first = (usePathname() ?? '').split('/').filter(Boolean)[0];
  const route = ROUTES.find((r) => r === first);
  useEffect(() => {
    document.title = route ? `${t(`pageTitle.${route}`)} | ${t('name')}` : t('name');
  }, [route, t]);
  return null;
}
