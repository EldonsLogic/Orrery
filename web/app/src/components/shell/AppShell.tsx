'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { Alert, Button } from '../../ui';
import { LoadingMark } from '../marks/LoadingMark';
import { SideNav } from './SideNav';
import { UserMenu } from './UserMenu';
import { WorkspaceSwitcher } from './WorkspaceSwitcher';
import { useSession } from './SessionProvider';
import { usesDrawer } from '../../lib/viewport';
import { usePathname } from 'next/navigation';
import Link from 'next/link';
import styles from './Shell.module.css';

/**
 * Top bar, side navigation (a drawer on narrow screens), skip link and the single main landmark. Pages inside render no <main>.
 * The top bar, navigation and the phone "Ask Seshna" dock are glass chrome (styles/foundation.css); content stays solid.
 */
export function AppShell({ children, brand }: { children: ReactNode; brand?: ReactNode }) {
  const t = useTranslations('shell');
  const pathname = usePathname() ?? '';
  const { session, switchFailed, dismissError, retry } = useSession();
  const [drawer, setDrawer] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!drawer) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setDrawer(false);
        toggle.current?.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [drawer]);

  // Leaving the narrow layout (rotate, resize) closes the drawer so it cannot reopen stale.
  useEffect(() => {
    const onResize = () => {
      if (!usesDrawer(window.innerWidth)) setDrawer(false);
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const skip = (
    <a href="#main" className={styles.skip}>
      {t('skip')}
    </a>
  );

  if (session.status !== 'ready') {
    return (
      <div className={styles.root}>
        {skip}
        <main id="main" tabIndex={-1} className={styles.stateMain}>
          {session.status === 'loading' ? <LoadingMark label={t('state.loading')} /> : null}
          {session.status === 'signedOut' ? (
            <Alert tone="info" title={t('state.signedOut.title')}>
              <p>{t('state.signedOut.body')}</p>
              <a className={styles.link} href="/login/">
                {t('state.signedOut.action')}
              </a>
            </Alert>
          ) : null}
          {session.status === 'error' ? (
            <Alert tone="danger" title={t('state.error.title')}>
              <p>{t('state.error.body')}</p>
              <Button onClick={retry}>{t('state.error.retry')}</Button>
            </Alert>
          ) : null}
        </main>
      </div>
    );
  }

  const { claims, memberships, displayName } = session;
  const noWorkspace = !memberships.some((m) => m.status === 'active');
  return (
    <div className={styles.root}>
      {skip}
      <header className={styles.topBar}>
        <button
          ref={toggle}
          type="button"
          className={styles.menuButton}
          aria-expanded={drawer}
          aria-controls="app-nav"
          onClick={() => setDrawer((v) => !v)}
        >
          {t('nav.toggle')}
        </button>
        {brand ? (
          <Link href="/home/" className={styles.brand} aria-label={t('nav.home')}>
            {brand}
          </Link>
        ) : null}
        <WorkspaceSwitcher claims={claims} memberships={memberships} />
        <UserMenu displayName={displayName} claims={claims} />
      </header>
      <div className={styles.body}>
        <div id="app-nav" className={styles.navWrap} data-open={drawer ? 'true' : 'false'}>
          <SideNav claims={claims} onNavigate={() => setDrawer(false)} />
        </div>
        <main id="main" tabIndex={-1} className={styles.main} inert={drawer}>
          {switchFailed ? (
            <Alert tone="danger" title={t('workspace.failedTitle')}>
              <p>{t('workspace.failedBody')}</p>
              <Button variant="secondary" onClick={dismissError}>
                {t('workspace.dismiss')}
              </Button>
            </Alert>
          ) : null}
          {noWorkspace ? (
            <Alert tone="warning" title={t('state.noWorkspace.title')}>
              {t('state.noWorkspace.body')}
            </Alert>
          ) : (
            <div className={styles.content}>{children}</div>
          )}
        </main>
      </div>
      {pathname.startsWith('/chat/') ? null : (
        <nav aria-label={t('dock.label')} className={styles.dock} inert={drawer}>
          <Link href="/chat/" className={styles.dockLink}>
            <span>{t.rich('dock.ask', { brand: (c) => <bdi>{c}</bdi> })}</span>
          </Link>
        </nav>
      )}
    </div>
  );
}
