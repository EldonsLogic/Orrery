'use client';

import { useLocale, useTranslations } from 'next-intl';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { Icon, Mark, type IconName } from '../../ui';
import { buildNav } from '../../lib/navigation';
import { BUILD_STAGES, stageProgress } from '../../lib/buildProgress';
import { callerOf, type SessionClaims } from '../../lib/session';
import { canViewBlueprint } from '../../blueprint/access';
import { canEditBranding } from '../../settings/branding/access';
import { fixtureBlueprint } from '../../blueprint/fixture';
import { fixtureData } from '../../records/fixture/rows';
import styles from './Shell.module.css';

// Icons through the one Icon component (placeholder set until the brand icon set exists); the label carries the meaning.
const ICONS: Readonly<Record<string, IconName>> = {
  home: 'home',
  chat: 'chat',
  blueprint: 'workflow',
  branding: 'palette',
  customer: 'users',
  item: 'package',
  sales_order: 'cart',
  sales_invoice: 'receipt',
};

export function SideNav({ claims, buildState, onNavigate }: { claims: SessionClaims; buildState?: string; onNavigate: () => void }) {
  const t = useTranslations('shell.nav');
  const tp = useTranslations('marks.progress');
  const locale = useLocale();
  const pathname = usePathname() ?? '';
  const caller = callerOf(claims);
  const sections = buildNav(fixtureData, caller, locale, { home: t('home') }).map((s) => {
    if (s.id !== 'workspace') return s;
    const extra = [{ id: 'chat', label: t('chat'), href: '/chat/' }];
    if (canViewBlueprint(fixtureBlueprint, caller)) extra.push({ id: 'blueprint', label: t('blueprint'), href: '/blueprint/' });
    if (canEditBranding(fixtureBlueprint, caller)) extra.push({ id: 'branding', label: t('branding'), href: '/settings/branding/' });
    return { ...s, items: [...s.items, ...extra] };
  });
  const hasRecords = sections.some((s) => s.id === 'records');
  // The plan status: the current build stage, or "Live" once every stage is done.
  const step = stageProgress(buildState);
  const live = step >= BUILD_STAGES.length;
  const stage = BUILD_STAGES[Math.min(step, BUILD_STAGES.length - 1)]!;
  return (
    <nav aria-label={t('label')} className={styles.nav}>
      {sections.map((s) => (
        <section key={s.id} aria-labelledby={`nav-${s.id}`} className={styles.navSection}>
          <h2 id={`nav-${s.id}`} className={styles.navHeading}>
            {t(`sections.${s.id}`)}
          </h2>
          <ul className={styles.navList}>
            {s.items.map((i) => {
              const current = pathname.startsWith(i.href);
              return (
                <li key={i.id}>
                  {/* data-label feeds the rail tooltip (CSS, hidden from assistive technology); the span is the accessible name. */}
                  <Link href={i.href} className={styles.navLink} data-label={i.label} aria-current={current ? 'page' : undefined} onClick={onNavigate}>
                    <Icon name={ICONS[i.id] ?? 'file'} size="md" className={styles.navIcon} />
                    <span className={styles.navText}>{i.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {hasRecords ? null : <p className={styles.navEmpty}>{t('empty')}</p>}
      {buildState ? (
        <div className={styles.navFooter}>
          <Mark upper="solid" lower={live ? 'solid' : 'outline'} size={20} />
          <span className={styles.navFooterText}>
            <span className={styles.navFooterLabel}>{tp('title')}</span>
            <span>{tp(`stage.${stage}`)}</span>
          </span>
        </div>
      ) : null}
    </nav>
  );
}
