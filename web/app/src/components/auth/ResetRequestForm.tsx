'use client';

import { useState, type FormEvent } from 'react';
import { useTranslations } from 'next-intl';
import { Alert, Button, Stack, TextField } from '../../ui';
import { placeholderResetRequest, type AuthResult, type ResetRequestHandler } from '../../lib/authPlaceholder';
import { AuthShell } from './AuthShell';
import styles from './Auth.module.css';

export type ResetRequestFormProps = {
  /** Defaults to the placeholder until PLT-005. */
  onSubmit?: ResetRequestHandler;
  /** Starting outcome, for tests and previews only. */
  initialResult?: AuthResult;
};

export function ResetRequestForm({ onSubmit = placeholderResetRequest, initialResult }: ResetRequestFormProps) {
  const t = useTranslations('auth');
  const [result, setResult] = useState<AuthResult | undefined>(initialResult);
  const [busy, setBusy] = useState(false);

  async function handle(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    setBusy(true);
    try {
      setResult(await onSubmit({ email: String(data.get('email') ?? '') }));
    } catch {
      setResult({ ok: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title={t('reset.title')}>
      {result?.ok ? (
        <Alert tone="success" title={t('reset.sentTitle')}>
          {t('reset.sent')}
        </Alert>
      ) : (
        <>
          <p className={styles.intro}>{t('reset.intro')}</p>
          <form onSubmit={handle}>
            <Stack gap={2}>
              {result && !result.ok ? (
                <Alert tone="danger" title={t('reset.errorTitle')}>
                  {t('reset.error')}
                </Alert>
              ) : null}
              <TextField name="email" type="email" label={t('reset.email')} autoComplete="username" required />
              <Button type="submit" loading={busy}>
                {busy ? t('reset.submitting') : t('reset.submit')}
              </Button>
            </Stack>
          </form>
        </>
      )}
      <a className={styles.link} href="/login/">
        {t('backToLogin')}
      </a>
    </AuthShell>
  );
}
