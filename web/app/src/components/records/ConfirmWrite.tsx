'use client';

import { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { Button, Card, Stack } from '../../ui';
import { inertOutside } from '../../ui/inert';
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
  const root = useRef<HTMLDivElement>(null);
  const live = useRef({ busy, onCancel });
  live.current = { busy, onCancel };
  // Modal behaviour: move focus in, make the rest of the page inert, restore both on close, Escape cancels, Tab stays inside.
  // Keys are handled on the document so they keep working when focus is not on a button (both buttons are disabled while busy).
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    const release = root.current ? inertOutside(root.current) : undefined;
    root.current?.querySelector<HTMLElement>('button')?.focus();
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      const box = root.current;
      if (!box) return;
      if (e.key === 'Escape' && !live.current.busy) {
        e.stopPropagation();
        live.current.onCancel();
      } else if (e.key === 'Tab') {
        const items = Array.from(box.querySelectorAll<HTMLElement>('button:not(:disabled)'));
        const active = document.activeElement;
        if (!items.length) { e.preventDefault(); box.focus(); return; }
        const first = items[0] as HTMLElement;
        const last = items[items.length - 1] as HTMLElement;
        if (!box.contains(active) || (e.shiftKey && (active === first || active === box))) { e.preventDefault(); (e.shiftKey ? last : first).focus(); }
        else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      release?.();
      before?.focus?.();
    };
  }, []);
  // While busy both buttons are disabled and focus is lost: keep it on the dialog itself, not on <body>.
  useEffect(() => {
    if (busy && !root.current?.contains(document.activeElement)) root.current?.focus();
  }, [busy]);
  return (
    <div className={styles.dialog} ref={root} tabIndex={-1}>
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
