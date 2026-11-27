'use client';

import { useEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Alert, Button, Card, Checkbox, Select, Stack, TextField, VisuallyHidden } from '../../../ui';
import { canEditDocumentTemplates } from '../../../settings/documents/access';
import { createDocumentTemplatesController } from '../../../settings/documents/controller';
import {
  FOOTER_LOCALES,
  FOOTER_MAX,
  LOCKED_REGIONS,
  LOGO_PLACEMENTS,
  TEMPLATE_KINDS,
  footerLocaleOk,
  createFakeDocumentTemplatesPort,
  type DocumentTemplatesPort,
  type DocumentTemplatesSettings,
  type LogoPlacement,
  type TemplateKind,
} from '../../../settings/documents/port';
import { fixtureBlueprint } from '../../../blueprint/fixture';
import { plainText } from '../../../factory/text';
import { callerOf } from '../../../lib/session';
import { useSession } from '../../shell/SessionProvider';
import styles from './DocumentTemplatesScreen.module.css';

/** Settings > Document templates (WEB-009). The session decides who may edit; data comes from a fake port until the gateway exists. */
export function DocumentTemplatesScreen({ portFor }: { portFor?: (tenantId: string) => DocumentTemplatesPort }) {
  const { session } = useSession();
  const t = useTranslations('documents');
  const tenantId = session.status === 'ready' ? session.claims.tenantId : null;
  // One port per workspace: nothing loaded or saved for one tenant can reach another.
  const port = useMemo(() => (tenantId === null ? null : (portFor ?? (() => createFakeDocumentTemplatesPort()))(tenantId)), [tenantId, portFor]);
  if (session.status !== 'ready' || !port || tenantId === null) return null;
  if (!canEditDocumentTemplates(fixtureBlueprint, callerOf(session.claims))) {
    return (
      <section aria-labelledby="documents-title">
        <h1 id="documents-title">{t('title')}</h1>
        <Alert tone="info" title={t('noAccess.title')}>
          {t('noAccess.body')}
        </Alert>
      </section>
    );
  }
  // The key throws the editor's state away on a workspace switch.
  return <DocumentTemplatesEditor key={tenantId} port={port} initial={null} />;
}

export function DocumentTemplatesEditor({ port, initial, initialKind = 'tax_invoice' }: { port: DocumentTemplatesPort; initial: DocumentTemplatesSettings | null; initialKind?: TemplateKind }) {
  const t = useTranslations('documents');
  const locale = useLocale();
  const [kind, setKind] = useState<TemplateKind>(initialKind);
  const ctrl = useMemo(() => createDocumentTemplatesController(port, initial), [port, initial]);
  useEffect(() => ctrl.attach(), [ctrl]);
  const { settings: cur, status, loaded } = useSyncExternalStore(ctrl.subscribe, ctrl.get, ctrl.get);
  const editable = loaded === 'ready';
  const filled = FOOTER_LOCALES.filter((l) => cur.footerText[l] !== '').length;
  const footerMixed = filled === 1;
  const regions = LOCKED_REGIONS[kind];
  const tenantFooter = plainText(cur.footerText[locale === 'ar' ? 'ar' : 'en'], FOOTER_MAX);

  return (
    <section aria-labelledby="documents-title" className={styles.page}>
      <header>
        <h1 id="documents-title">{t('title')}</h1>
        <p>{t('intro')}</p>
      </header>
      <nav aria-label={t('list')}>
        <ul className={styles.kinds}>
          {TEMPLATE_KINDS.map((k) => (
            <li key={k}>
              <button type="button" className={styles.kind} aria-current={k === kind ? 'true' : undefined} onClick={() => setKind(k)}>
                {t(`kinds.${k}`)}
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <div className={styles.layout}>
        <Stack>
          <Card as="section" aria-label={t('settings')}>
            <Stack>
              <Select label={t('logo.label')} value={cur.logoPosition} disabled={!editable} onChange={(e) => ctrl.edit({ logoPosition: e.target.value as LogoPlacement })}>
                {LOGO_PLACEMENTS.map((p) => (
                  <option key={p} value={p}>
                    {t(`logo.${p}`)}
                  </option>
                ))}
              </Select>
              <Checkbox label={t('accent.label')} hint={t('accent.hint')} checked={cur.accentOnDocuments} disabled={!editable} onChange={(e) => ctrl.edit({ accentOnDocuments: e.target.checked })} />
              {FOOTER_LOCALES.map((l) => (
                <TextField
                  key={l}
                  label={t(`footer.label.${l}`)}
                  hint={t('footer.hint', { max: FOOTER_MAX })}
                  value={cur.footerText[l]}
                  dir={l === 'ar' ? 'rtl' : 'ltr'}
                  disabled={!editable}
                  maxLength={FOOTER_MAX}
                  onChange={(e) => ctrl.edit({ footerText: { ...cur.footerText, [l]: e.target.value } })}
                  error={footerLocaleOk(cur.footerText[l]) ? (footerMixed && cur.footerText[l] === '' ? t('footer.both') : undefined) : t('footer.invalid')}
                />
              ))}
            </Stack>
          </Card>
          <Card as="section" aria-labelledby="documents-locked">
            <h2 id="documents-locked">{t('locked.title')}</h2>
            <p>{t('locked.note')}</p>
            <ul className={styles.locked}>
              {regions.map((r) => (
                <li key={r} data-locked-region={r}>
                  {t(`regions.${r}`)} <span className={styles.lock}>{t('locked.badge')}</span>
                </li>
              ))}
            </ul>
          </Card>
        </Stack>
        <section aria-labelledby="documents-preview">
          <h2 id="documents-preview">{t('preview.title')}</h2>
          <p>{t('preview.note')}</p>
          <div className={styles.paper} data-accent={cur.accentOnDocuments ? 'on' : 'off'} role="group" aria-label={t(`kinds.${kind}`)}>
            {regions.map((r) => (
              <div key={r} data-locked-region={r} className={r === 'header' ? styles.header : r === 'lines' ? styles.lines : styles.region}>
                {r === 'header' ? (
                  <div className={styles.logoRow} data-placement={cur.logoPosition}>
                    <span className={styles.logo}>{t('preview.logo')}</span>
                  </div>
                ) : null}
                <strong className={styles.regionName}>{t(`regions.${r}`)}</strong>
                <span>{t(`preview.sample.${r}`)}</span>
                {r === 'footer' && tenantFooter ? <span className={styles.footerText}>{tenantFooter}</span> : null}
              </div>
            ))}
          </div>
        </section>
      </div>
      <VisuallyHidden role="status">{status === 'saved' ? t('saved') : ''}</VisuallyHidden>
      {loaded === 'loading' ? <Alert tone="info">{t('loading')}</Alert> : null}
      {loaded === 'failed' ? <Alert tone="danger">{t('loadFailed')}</Alert> : null}
      <div className={styles.actions}>
        <Button onClick={() => void ctrl.save()} loading={status === 'saving'} disabled={!editable || !ctrl.valid()}>
          {status === 'saving' ? t('saving') : t('save')}
        </Button>
      </div>
      <div aria-live="polite">
        {status === 'saved' ? <Alert tone="success">{t('saved')}</Alert> : null}
        {status === 'forbidden' ? <Alert tone="danger">{t('errForbidden')}</Alert> : null}
        {status === 'invalid' ? <Alert tone="danger">{t('errInvalid')}</Alert> : null}
        {status === 'failed' ? <Alert tone="danger">{t('errFailed')}</Alert> : null}
      </div>
    </section>
  );
}
