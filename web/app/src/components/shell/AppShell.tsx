'use client';

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { Alert, Button, Icon } from '../../ui';
import { LoadingMark } from '../marks/LoadingMark';
import { SideNav } from './SideNav';
import { UserMenu } from './UserMenu';
import { LanguageSwitch } from './LanguageSwitch';
import { WorkspaceSwitcher } from './WorkspaceSwitcher';
import { useSession } from './SessionProvider';
import { InlineAskContext } from './inlineAsk';
import { usesDrawer, usesRail } from '../../lib/viewport';
import { dockShown, keyboardOpen } from '../../lib/dock';
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
  // Tablet icon rail: collapsed by default, expanded by its toggle (keyboard focus inside also expands it, in CSS).
  const [rail, setRail] = useState(false);
  const [keyboard, setKeyboard] = useState(false);
  const [inlineAsk, setInlineAsk] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const railToggle = useRef<HTMLButtonElement>(null);
  const onChat = pathname.startsWith('/chat');
  const reportInlineAsk = useCallback((inView: boolean) => setInlineAsk(inView), []);

  useEffect(() => {
    if (!drawer && !rail) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (drawer) {
        setDrawer(false);
        toggle.current?.focus();
      } else {
        setRail(false);
        railToggle.current?.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [drawer, rail]);

  // Leaving a layout (rotate, resize) closes its drawer or rail so neither can reopen stale.
  useEffect(() => {
    const onResize = () => {
      if (!usesDrawer(window.innerWidth)) setDrawer(false);
      if (!usesRail(window.innerWidth)) setRail(false);
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // The on-screen keyboard (visual viewport shrinks) hides the phone dock so it never sits on the field being typed in.
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const onVv = () => setKeyboard(keyboardOpen(window.innerHeight, vv.height));
    vv.addEventListener('resize', onVv);
    return () => vv.removeEventListener('resize', onVv);
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
          <Icon name="menu" size="md" />
          <span className={styles.switcherLabel}>{t('nav.toggle')}</span>
        </button>
        {brand ? (
          <Link href="/home/" className={styles.brand} aria-label={t('nav.home')}>
            {brand}
          </Link>
        ) : null}
        <WorkspaceSwitcher claims={claims} memberships={memberships} />
        <LanguageSwitch />
        <UserMenu displayName={displayName} claims={claims} />
      </header>
      <div className={styles.body}>
        <div id="app-nav" className={styles.navWrap} data-open={drawer ? 'true' : 'false'} data-rail={rail ? 'expanded' : 'collapsed'}>
          <div className={styles.navInner}>
            <button
              ref={railToggle}
              type="button"
              className={styles.railToggle}
              aria-expanded={rail}
              aria-controls="app-nav"
              onClick={() => setRail((v) => !v)}
            >
              <Icon name={rail ? 'railCollapse' : 'railExpand'} size="md" />
              <span className={styles.switcherLabel}>{t(rail ? 'nav.collapse' : 'nav.expand')}</span>
            </button>
            <SideNav
              claims={claims}
              buildState={memberships.find((m) => m.tenantId === claims.tenantId)?.buildState}
              onNavigate={() => {
                setDrawer(false);
                setRail(false);
              }}
            />
          </div>
        </div>
        <main id="main" tabIndex={-1} className={styles.main} data-screen={onChat ? 'chat' : undefined} inert={drawer}>
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
            <InlineAskContext.Provider value={reportInlineAsk}>
              <div className={styles.content}>{children}</div>
            </InlineAskContext.Provider>
          )}
        </main>
      </div>
      {onChat ? null : (
        <nav
          aria-label={t('dock.label')}
          className={styles.dock}
          data-hidden={dockShown({ onChat, keyboard, inlineAskInView: inlineAsk }) ? undefined : 'true'}
          inert={drawer || keyboard || inlineAsk}
        >
          <Link href="/chat/" className={styles.dockLink}>
            <span>{t.rich('dock.ask', { brand: (c) => <bdi>{c}</bdi> })}</span>
          </Link>
        </nav>
      )}
    </div>
  );
}
