'use client';

import { useEffect, useMemo, useState, useSyncExternalStore, type CSSProperties } from 'react';
import { useTranslations } from 'next-intl';
import { Alert, Button, Card, Select, Stack, TextField, VisuallyHidden } from '../../../ui';
import { canEditDocumentTemplates } from '../../../settings/documents/access';
import { createDocumentTemplatesController } from '../../../settings/documents/controller';
import {
  ACCENT_TOKENS,
  FOOTER_MAX,
  LOCKED_REGIONS,
  LOGO_PLACEMENTS,
  TEMPLATE_KINDS,
  checkTemplate,
  createFakeDocumentTemplatesPort,
  type AccentToken,
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
  const [kind, setKind] = useState<TemplateKind>(initialKind);
  const ctrl = useMemo(() => createDocumentTemplatesController(port, initial), [port, initial]);
  useEffect(() => ctrl.attach(), [ctrl]);
  const { settings, status, loaded } = useSyncExternalStore(ctrl.subscribe, ctrl.get, ctrl.get);
  const editable = loaded === 'ready';
  const cur = settings[kind];
  const footerOk = checkTemplate(cur);
  const regions = LOCKED_REGIONS[kind];
  const previewStyle = { '--doc-accent': cur.accent === 'accent' ? 'var(--color-accent)' : 'var(--color-primary)' } as CSSProperties;

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
              <h2>{t(`kinds.${kind}`)}</h2>
              <Select label={t('logo.label')} value={cur.logoPlacement} disabled={!editable} onChange={(e) => ctrl.edit(kind, { logoPlacement: e.target.value as LogoPlacement })}>
                {LOGO_PLACEMENTS.map((p) => (
                  <option key={p} value={p}>
                    {t(`logo.${p}`)}
                  </option>
                ))}
              </Select>
              <Select label={t('accent.label')} hint={t('accent.hint')} value={cur.accent} disabled={!editable} onChange={(e) => ctrl.edit(kind, { accent: e.target.value as AccentToken })}>
                {ACCENT_TOKENS.map((a) => (
                  <option key={a} value={a}>
                    {t(`accent.${a}`)}
                  </option>
                ))}
              </Select>
              <TextField
                label={t('footer.label')}
                hint={t('footer.hint', { max: FOOTER_MAX })}
                value={cur.footerText}
                disabled={!editable}
                maxLength={FOOTER_MAX}
                onChange={(e) => ctrl.edit(kind, { footerText: e.target.value })}
                error={footerOk ? undefined : t('footer.invalid')}
              />
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
          <div className={styles.paper} style={previewStyle} role="group" aria-label={t(`kinds.${kind}`)}>
            {regions.map((r) => (
              <div key={r} data-locked-region={r} className={r === 'header' ? styles.header : styles.region}>
                {r === 'header' ? (
                  <div className={styles.logoRow} data-placement={cur.logoPlacement}>
                    <span className={styles.logo}>{t('preview.logo')}</span>
                  </div>
                ) : null}
                <strong className={styles.regionName}>{t(`regions.${r}`)}</strong>
                <span>{t(`preview.sample.${r}`)}</span>
              </div>
            ))}
            {cur.footerText ? <p className={styles.footer}>{plainText(cur.footerText, FOOTER_MAX)}</p> : null}
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
