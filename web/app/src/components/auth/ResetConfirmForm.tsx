'use client';

import { useState, type FormEvent } from 'react';
import { useTranslations } from 'next-intl';
import { Alert, Button, Stack, TextField } from '../../ui';
import { placeholderResetConfirm, type AuthResult, type ResetConfirmHandler } from '../../lib/authPlaceholder';
import { AuthShell } from './AuthShell';
import styles from './Auth.module.css';

export type ResetConfirmFormProps = {
  /** Defaults to the placeholder until PLT-005. */
  onSubmit?: ResetConfirmHandler;
  /** Starting outcome, for tests and previews only. */
  initialResult?: AuthResult;
};

export function ResetConfirmForm({ onSubmit = placeholderResetConfirm, initialResult }: ResetConfirmFormProps) {
  const t = useTranslations('auth');
  const [result, setResult] = useState<AuthResult | undefined>(initialResult);
  const [mismatch, setMismatch] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handle(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const password = String(data.get('password') ?? '');
    if (password !== String(data.get('confirm') ?? '')) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    setBusy(true);
    try {
      setResult(await onSubmit({ password }));
    } catch {
      setResult({ ok: false });
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell title={t('confirm.title')}>
      {result?.ok ? (
        <Alert tone="success" title={t('confirm.doneTitle')}>
          {t('confirm.done')}
        </Alert>
      ) : (
        <>
          <p className={styles.intro}>{t('confirm.intro')}</p>
          <form onSubmit={handle}>
            <Stack gap={2}>
              {result && !result.ok ? (
                <Alert tone="danger" title={t('confirm.errorTitle')}>
                  {t('confirm.error')}
                </Alert>
              ) : null}
              <TextField name="password" type="password" label={t('confirm.password')} autoComplete="new-password" required />
              <TextField
                name="confirm"
                type="password"
                label={t('confirm.confirm')}
                autoComplete="new-password"
                error={mismatch ? t('confirm.mismatch') : undefined}
                required
              />
              <Button type="submit" loading={busy}>
                {busy ? t('confirm.submitting') : t('confirm.submit')}
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
