'use client';

import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronsUpDown } from 'lucide-react';
import { LoadingMark } from '../marks/LoadingMark';
import type { SessionClaims, WorkspaceMembership } from '../../lib/session';
import { useSession } from './SessionProvider';
import styles from './Shell.module.css';

const initial = (name: string) => [...name.trim()][0]?.toUpperCase() ?? '';

/**
 * One token per tenant (ADR-0007): picking a workspace asks for that tenant's token. A button opens a listbox (glass popover);
 * arrows, Home and End move, Enter or Space picks, Escape closes and returns focus. Suspended memberships are listed but disabled.
 */
export function WorkspaceSwitcher({ claims, memberships }: { claims: SessionClaims; memberships: ReadonlyArray<WorkspaceMembership> }) {
  const t = useTranslations('shell.workspace');
  const id = useId();
  const { switchWorkspace, switching } = useSession();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const current = memberships.find((m) => m.tenantId === claims.tenantId);
  const usable = memberships.map((m) => m.status === 'active');
  const disabled = switching || memberships.length < 2;

  useEffect(() => {
    if (!open) return;
    list.current?.focus();
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const show = () => {
    setActive(Math.max(0, memberships.findIndex((m) => m.tenantId === claims.tenantId)));
    setOpen(true);
  };
  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };
  const pick = (i: number) => {
    const m = memberships[i];
    if (!m || !usable[i]) return;
    close();
    if (m.tenantId !== claims.tenantId) void switchWorkspace(m.tenantId);
  };
  const step = (from: number, dir: 1 | -1) => {
    for (let i = from + dir; i >= 0 && i < memberships.length; i += dir) if (usable[i]) return i;
    return from;
  };
  const onKey = (e: KeyboardEvent) => {
    const keys: Record<string, () => void> = {
      ArrowDown: () => setActive((a) => step(a, 1)),
      ArrowUp: () => setActive((a) => step(a, -1)),
      Home: () => setActive(step(-1, 1)),
      End: () => setActive(step(memberships.length, -1)),
      Enter: () => pick(active),
      ' ': () => pick(active),
      Escape: close,
      Tab: () => setOpen(false),
    };
    const run = keys[e.key];
    if (!run) return;
    if (e.key !== 'Tab') e.preventDefault();
    run();
  };

  return (
    <div className={styles.switcher} ref={root}>
      <span id={`${id}-label`} className={styles.switcherLabel}>
        {t('label')}
      </span>
      <button
        ref={trigger}
        type="button"
        className={styles.switchButton}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-labelledby={`${id}-label ${id}-name`}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            show();
          }
        }}
      >
        <span aria-hidden="true" className={styles.orgAvatar}>
          {initial(current?.name ?? '')}
        </span>
        <span id={`${id}-name`} className={styles.switchName} dir="auto">
          {current?.name}
        </span>
        <ChevronsUpDown aria-hidden="true" className={styles.chevron} />
      </button>
      <ul
        ref={list}
        id={`${id}-list`}
        role="listbox"
        tabIndex={-1}
        aria-labelledby={`${id}-label`}
        aria-activedescendant={open ? `${id}-opt-${active}` : undefined}
        className={styles.popover}
        hidden={!open}
        onKeyDown={onKey}
      >
        {memberships.map((m, i) => (
          <li
            key={m.tenantId}
            id={`${id}-opt-${i}`}
            role="option"
            aria-selected={m.tenantId === claims.tenantId}
            aria-disabled={m.status !== 'active' || undefined}
            data-active={open && i === active ? 'true' : undefined}
            className={styles.option}
            onMouseEnter={() => usable[i] && setActive(i)}
            onClick={() => pick(i)}
          >
            <span aria-hidden="true" className={styles.orgAvatar}>
              {initial(m.name)}
            </span>
            <span>{m.status === 'active' ? <bdi>{m.name}</bdi> : t('suspended', { name: `\u2068${m.name}\u2069` })}</span>
          </li>
        ))}
      </ul>
      {switching ? <LoadingMark label={t('switching')} /> : null}
    </div>
  );
}
