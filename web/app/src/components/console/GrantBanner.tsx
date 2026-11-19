'use client';

import { useTranslations } from 'next-intl';
import { Alert, Button } from '../../ui';
import { buildGrantBanner } from '../../console/banner';
import { formatClock } from '../../console/grants';
import { useConsole } from './ConsoleProvider';
import styles from './Console.module.css';

/** Always visible while a staff member is inside a tenant under an approved grant. */
export function GrantBanner() {
  const t = useTranslations('console.banner');
  const ts = useTranslations('console.scope');
  const { data, session, now, activeTenantId, leaveTenant } = useConsole();
  if (session.status !== 'ready') return null;
  const b = buildGrantBanner(data.grants, data.tenants, session.staffId, activeTenantId, now);
  if (!b) return null;
  return (
    <Alert tone={b.low ? 'danger' : 'warning'} title={t('title', { tenant: b.tenantName })} role="status">
      <p>
        {t('body')} {t('scope', { scope: b.scope.map((s) => ts(s)).join(', ') })}
      </p>
      {/* The live region announces the title and scope once, then only when a threshold is crossed
          (low, critical). The ticking clock is a timer with aria-live off, so it is never announced. */}
      {b.low ? <p>{b.critical ? t('critical') : t('low')}</p> : null}
      <p className={styles.countdown} role="timer" aria-live="off">
        {t('timeLeft')} <bdi dir="ltr">{formatClock(b.remaining)}</bdi>
      </p>
      <Button variant="secondary" onClick={leaveTenant}>
        {t('leave')}
      </Button>
    </Alert>
  );
}
