'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';

const ROUTES = ['home', 'chat', 'blueprint', 'onboarding', 'records', 'console', 'login', 'reset-password'] as const;

/** Page title with the product name isolated (U+2068 FSI ... U+2069 PDI), the plain-text form of <bdi>, so the Latin name never reorders an Arabic title. */
export const composeTitle = (page: string | null, name: string): string => {
  const isolated = `\u2068${name}\u2069`;
  return page ? `${page} | ${isolated}` : isolated;
};

/** Sets a per-route document title in the active language (WCAG 2.4.2). Unknown routes keep the default title. */
export function RouteTitle() {
  const t = useTranslations('pwa');
  const first = (usePathname() ?? '').split('/').filter(Boolean)[0];
  const route = ROUTES.find((r) => r === first);
  useEffect(() => {
    document.title = composeTitle(route ? t(`pageTitle.${route}`) : null, t('name'));
  }, [route, t]);
  return null;
}
