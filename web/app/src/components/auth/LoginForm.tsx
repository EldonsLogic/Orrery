'use client';

import { useState, type FormEvent, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { Alert, Button, Stack, TextField } from '../../ui';
import { placeholderLogin, type AuthResult, type LoginHandler } from '../../lib/authPlaceholder';
import { AuthShell } from './AuthShell';
import styles from './Auth.module.css';

export type LoginFormProps = {
  /** Defaults to the placeholder until PLT-005. */
  onSubmit?: LoginHandler;
  /** Starting outcome, for tests and previews only. */
  initialResult?: AuthResult;
  /** Tenant look (WEB-008): brand block above the title and the scoping tenant slug. */
  brand?: ReactNode;
  tenant?: string;
};

export function LoginForm({ onSubmit = placeholderLogin, initialResult, brand, tenant }: LoginFormProps) {
  const t = useTranslations('auth');
  const [result, setResult] = useState<AuthResult | undefined>(initialResult);
  const [busy, setBusy] = useState(false);

  async function handle(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setBusy(true);
    try {
      setResult(await onSubmit({ email: String(data.get('email') ?? ''), password: String(data.get('password') ?? '') }));
    } catch {
      setResult({ ok: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title={t('login.title')} brand={brand} tenant={tenant}>
      <p className={styles.intro}>{t('login.intro')}</p>
      <form onSubmit={handle} noValidate={false}>
        <Stack gap={2}>
          {result && !result.ok ? (
            <Alert tone="danger" title={t('login.errorTitle')}>
              {t('login.error')}
            </Alert>
          ) : null}
          <TextField name="email" type="email" label={t('login.email')} autoComplete="username" required />
          <TextField name="password" type="password" label={t('login.password')} autoComplete="current-password" required />
          <Button type="submit" loading={busy}>
            {busy ? t('login.submitting') : t('login.submit')}
          </Button>
          <a className={styles.link} href="/reset-password/">
            {t('login.forgot')}
          </a>
        </Stack>
      </form>
    </AuthShell>
  );
}
