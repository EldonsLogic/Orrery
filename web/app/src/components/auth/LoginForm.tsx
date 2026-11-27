'use client';

import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
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
  // False in server output and until this component has mounted in the browser. Until then the form cannot be
  // filled in or sent, so a failed hydration can never submit credentials natively.
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);

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
      {/* POST with a fixed same-page action: even a native submit never puts the email or password in a URL (GET).
          CSRF protection is added when identity is wired (PLT-005); today the handler is a placeholder. */}
      <form method="post" action="/login/" onSubmit={handle} noValidate={false}>
        <Stack gap={2}>
          {result && !result.ok ? (
            <Alert tone="danger" title={t('login.errorTitle')}>
              {t('login.error')}
            </Alert>
          ) : null}
          <TextField name="email" type="email" label={t('login.email')} autoComplete="username" required disabled={!ready} />
          <TextField name="password" type="password" label={t('login.password')} autoComplete="current-password" required disabled={!ready} />
          <Button type="submit" loading={busy} disabled={!ready}>
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
