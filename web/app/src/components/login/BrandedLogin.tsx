'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { LoginForm } from '../auth/LoginForm';
import { defaultLocale, isLocale } from '../../i18n';
import { brandingCss, isTenantKey, pickText, sanitiseBranding, type TenantBranding, type TenantBrandingPort } from './branding';
import { fakeBrandingPort } from './fake';
import styles from './BrandedLogin.module.css';

export type BrandedLoginProps = {
  port?: TenantBrandingPort;
  /** Tenant key; when absent it is read from the `tenant` query parameter in the browser. */
  tenantKey?: string;
  /** Starting branding, for tests and previews only. */
  initialBranding?: TenantBranding | null;
};

/** Brand block: tenant logo and name, or the platform look when there is no usable branding. */
export function BrandBlock({ branding }: { branding: TenantBranding | null }) {
  const t = useTranslations('auth');
  const raw = useLocale();
  const locale = isLocale(raw) ? raw : defaultLocale;
  const name = branding ? pickText(branding.displayName, locale) : null;
  const headline = branding ? pickText(branding.headline, locale) : null;
  const logo = branding?.showLogo !== false ? branding?.logo : undefined;

  if (!branding) {
    return (
      <div className={styles.brand}>
        <img className={styles.logo} src="/icons/app-icon.svg" alt="" width={40} height={40} />
        <p className={styles.name}>{t('login.platformName')}</p>
      </div>
    );
  }
  return (
    <div className={styles.brand}>
      {logo ? (
        <span className={logo.onDark ? styles.hasDark : undefined}>
          {/* Decorative: the name next to it carries the meaning. */}
          <img className={`${styles.logo} ${styles.logoLight}`} src={logo.onLight} alt="" referrerPolicy="no-referrer" />
          {logo.onDark ? (
            <img className={`${styles.logo} ${styles.logoDark}`} src={logo.onDark} alt="" referrerPolicy="no-referrer" />
          ) : null}
        </span>
      ) : null}
      {name ? <p className={styles.name}>{name}</p> : null}
      {headline ? <p className={styles.headline}>{headline}</p> : null}
    </div>
  );
}

export function BrandedLogin({ port = fakeBrandingPort, tenantKey, initialBranding }: BrandedLoginProps) {
  const [branding, setBranding] = useState<TenantBranding | null>(sanitiseBranding(initialBranding));

  useEffect(() => {
    const key = tenantKey ?? new URLSearchParams(window.location.search).get('tenant');
    if (!isTenantKey(key)) {
      setBranding(null);
      return;
    }
    let live = true;
    port
      .load(key)
      .then((b) => live && setBranding(b && b.slug === key ? sanitiseBranding(b) : null))
      .catch(() => live && setBranding(null)); // any failure: platform look, never a broken page
    return () => {
      live = false;
    };
  }, [port, tenantKey]);

  return (
    <>
      {/* CSS built from sanitised tokens only (no `<`, quotes or braces can reach it); React would HTML-escape a text child. */}
      {branding ? <style dangerouslySetInnerHTML={{ __html: brandingCss(branding) }} /> : null}
      <LoginForm brand={<BrandBlock branding={branding} />} tenant={branding?.slug} />
    </>
  );
}
