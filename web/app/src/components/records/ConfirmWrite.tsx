'use client';

import { useTranslations } from 'next-intl';
import { Button, Card, Stack } from '../../ui';
import type { Change } from '../../records/actions';
import styles from './Records.module.css';

export type ConfirmWriteProps = {
  /** Action name, already resolved (tool or transition label). */
  actionLabel: string;
  entityLabel: string;
  recordId?: string;
  risk: string;
  /** Plain summary of what will change; empty for actions that change state only. */
  changes: ReadonlyArray<{ label: string } & Change>;
  /** The action touches the ledger, tax or sends something outside. */
  sensitive: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/** Confirm-before-write for R2 actions. It only asks; the write itself goes through submitAction. */
export function ConfirmWrite({ actionLabel, entityLabel, recordId, risk, changes, sensitive, busy, onConfirm, onCancel }: ConfirmWriteProps) {
  const t = useTranslations('records.confirm');
  return (
    <div className={styles.dialog}>
      <Card as="section" role="dialog" aria-modal="true" aria-labelledby="confirm-title" className={styles.dialogBody}>
        <Stack gap={2}>
          <h2 id="confirm-title" className={styles.title}>{t('title', { action: actionLabel })}</h2>
          <p>{recordId ? t('intro', { action: actionLabel, entity: entityLabel, id: recordId }) : t('introNew', { action: actionLabel, entity: entityLabel })}</p>
          <p>{t('risk', { risk })}</p>
          {sensitive ? <p>{t('sensitive')}</p> : null}
          {changes.length ? (
            <ul className={styles.changes} aria-label={t('changes')}>
              {changes.map((c) => (
                <li key={c.fieldId}>
                  {t('change', { field: c.label, before: c.before || t('empty'), after: c.after || t('empty') })}
                </li>
              ))}
            </ul>
          ) : (
            <p>{t('noChanges')}</p>
          )}
          <Stack direction="row" gap={1} wrap>
            <Button onClick={onConfirm} loading={busy}>{t('confirm')}</Button>
            <Button variant="secondary" onClick={onCancel} disabled={busy}>{t('back')}</Button>
          </Stack>
        </Stack>
      </Card>
    </div>
  );
}
