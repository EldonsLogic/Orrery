'use client';

import { useId } from 'react';
import { useTranslations } from 'next-intl';
import { Spinner } from '../../ui';
import type { SessionClaims, WorkspaceMembership } from '../../lib/session';
import { useSession } from './SessionProvider';
import styles from './Shell.module.css';

/** One token per tenant (ADR-0007): picking a workspace asks for that tenant's token. Suspended memberships are listed but disabled. */
export function WorkspaceSwitcher({ claims, memberships }: { claims: SessionClaims; memberships: ReadonlyArray<WorkspaceMembership> }) {
  const t = useTranslations('shell.workspace');
  const id = useId();
  const { switchWorkspace, switching } = useSession();
  return (
    <div className={styles.switcher}>
      <label htmlFor={id} className={styles.switcherLabel}>
        {t('label')}
      </label>
      <select
        id={id}
        className={styles.select}
        value={claims.tenantId}
        disabled={switching || memberships.length < 2}
        onChange={(e) => void switchWorkspace(e.target.value)}
      >
        {memberships.map((m) => (
          <option key={m.tenantId} value={m.tenantId} disabled={m.status !== 'active'}>
            {m.status === 'active' ? m.name : t('suspended', { name: m.name })}
          </option>
        ))}
      </select>
      {switching ? <Spinner label={t('switching')} /> : null}
    </div>
  );
}
