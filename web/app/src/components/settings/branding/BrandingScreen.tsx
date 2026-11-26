'use client';

import { useEffect, useId, useMemo, useSyncExternalStore, type CSSProperties } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Alert, Button, Card, Stack, TextField, VisuallyHidden } from '../../../ui';
import { canEditBranding } from '../../../settings/branding/access';
import { DEFAULT_PRIMARY, derive, normHex, rawPairs, type Pair, type Theme } from '../../../settings/branding/colour';
import { createBrandingController } from '../../../settings/branding/controller';
import { createFakeBrandingPort, type BrandingPort, type BrandingSettings } from '../../../settings/branding/port';
import { fixtureBlueprint } from '../../../blueprint/fixture';
import { plainText } from '../../../factory/text';
import { callerOf } from '../../../lib/session';
import { useSession } from '../../shell/SessionProvider';
import styles from './BrandingScreen.module.css';

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** Settings > Branding (WEB-007). The session decides who may edit; the data comes from a fake port until the gateway exists. */
export function BrandingScreen({ portFor }: { portFor?: (tenantId: string) => BrandingPort }) {
  const { session } = useSession();
  const t = useTranslations('branding');
  const tenantId = session.status === 'ready' ? session.claims.tenantId : null;
  // One port per workspace: nothing loaded or saved for one tenant can reach another.
  const port = useMemo(() => (tenantId === null ? null : (portFor ?? (() => createFakeBrandingPort()))(tenantId)), [tenantId, portFor]);
  if (session.status !== 'ready' || !port || tenantId === null) return null;
  if (!canEditBranding(fixtureBlueprint, callerOf(session.claims))) {
    return (
      <section aria-labelledby="branding-title">
        <h1 id="branding-title">{t('title')}</h1>
        <Alert tone="info" title={t('noAccess.title')}>
          {t('noAccess.body')}
        </Alert>
      </section>
    );
  }
  // The key throws the editor's state away on a workspace switch.
  return <BrandingEditor key={tenantId} port={port} initial={null} />;
}

export function BrandingEditor({ port, initial }: { port: BrandingPort; initial: BrandingSettings | null }) {
  const t = useTranslations('branding');
  const tr = t as unknown as Translate;
  const locale = useLocale();
  const nf = useMemo(() => new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }), [locale]);
  const ctrl = useMemo(() => createBrandingController(port, initial), [port, initial]);
  useEffect(() => ctrl.attach(), [ctrl]);
  const { text, logo, logoError, status, loaded } = useSyncExternalStore(ctrl.subscribe, ctrl.get, ctrl.get);
  const logoId = useId();
  const editable = loaded === 'ready';

  const result = useMemo(() => derive(text), [text]);
  const raw = useMemo(() => rawPairs(text), [text]);
  const valid = result.status === 'ok';
  const picked = normHex(text);

  const onSave = () => {
    if (picked && valid) void ctrl.save(picked);
  };
  const onLogo = (file: File | undefined) => {
    if (file) void ctrl.uploadLogo({ fileName: file.name, mediaType: file.type, sizeBytes: file.size });
  };

  const pairLabel = (id: string) => {
    const [key, surface] = id.split('/');
    return tr(`pairs.${key}`, { surface: surface ? tr(`surfaces.${surface}`) : '' });
  };
  const panel = (mode: 'light' | 'dark', theme: Theme, adjusted: boolean) => {
    const style = { ...theme.vars } as CSSProperties;
    return (
      <div key={mode} className={styles.panel} style={style} role="group" aria-label={t(`preview.${mode}`)}>
        <strong>{t(`preview.${mode}`)}</strong>
        <div className={styles.panelCard}>
          <span>{t('preview.card')}</span>
          <span className={styles.pLink}>{t('preview.link')}</span>
          <span className={styles.pBtn}>{t('preview.button')}</span>
        </div>
        <span>
          <span className={styles.swatch} style={{ background: theme.primary }} aria-hidden="true" /> <bdi dir="ltr">{theme.primary}</bdi>
        </span>
        {adjusted ? <small>{tr('preview.adjusted', { colour: theme.primary })}</small> : null}
      </div>
    );
  };
  // A valid hex that was refused: show the pairs it fails as picked, with the ratio and the minimum.
  const failedList = (r: NonNullable<typeof raw>) => {
    const failed = (['light', 'dark'] as const).flatMap((mode) => r[mode].filter((p) => !p.ok).map((p) => ({ mode, p })));
    if (failed.length === 0) return null;
    return (
      <section aria-labelledby="branding-failed">
        <h2 id="branding-failed">{t('result.failedTitle')}</h2>
        <ul className={styles.failed}>
          {failed.map(({ mode, p }) => (
            <li key={`${mode}/${p.id}`}>
              {tr('result.failedPair', {
                pair: pairLabel(p.id),
                theme: t(`themeName.${mode}`),
                fg: p.fg,
                bg: p.bg,
                ratio: tr('result.ratioValue', { value: nf.format(p.ratio) }),
                min: tr('result.ratioValue', { value: nf.format(p.min) }),
              })}
            </li>
          ))}
        </ul>
      </section>
    );
  };
  const table = (mode: 'light' | 'dark', pairs: ReadonlyArray<Pair>, rawPairsOfMode: ReadonlyArray<Pair> | undefined) => (
    <table key={mode} className={styles.pairs}>
      <caption>
        {tr('result.summary', { pass: pairs.filter((p) => p.ok).length, total: pairs.length, theme: t(`themeName.${mode}`) })}
        {rawPairsOfMode ? ' ' + tr('result.rawSummary', { pass: rawPairsOfMode.filter((p) => p.ok).length, total: rawPairsOfMode.length }) : ''}
      </caption>
      <thead>
        <tr>
          <th scope="col">{t('result.pair')}</th>
          <th scope="col">{t('result.ratio')}</th>
          <th scope="col">{t('result.min')}</th>
          <th scope="col">{t('result.result')}</th>
        </tr>
      </thead>
      <tbody>
        {pairs.map((p) => (
          <tr key={p.id}>
            <th scope="row">{pairLabel(p.id)}</th>
            <td className={styles.num}>{tr('result.ratioValue', { value: nf.format(p.ratio) })}</td>
            <td className={styles.num}>{tr('result.ratioValue', { value: nf.format(p.min) })}</td>
            <td>{p.ok ? t('result.pass') : t('result.fail')}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <section aria-labelledby="branding-title" className={styles.page}>
      <header>
        <h1 id="branding-title">{t('title')}</h1>
        <p>{t('intro')}</p>
      </header>
      <div className={styles.layout}>
        <Card as="section" aria-label={t('settings')}>
          <Stack>
            <div className={styles.row}>
              <input
                type="color"
                className={styles.picker}
                aria-label={t('colour.picker')}
                value={(picked ?? DEFAULT_PRIMARY).toLowerCase()}
                onChange={(e) => ctrl.setText(e.target.value.toUpperCase())}
                disabled={!editable}
              />
              <TextField
                label={t('colour.label')}
                hint={t('colour.hint')}
                value={text}
                onChange={(e) => ctrl.setText(e.target.value)}
                disabled={!editable}
                dir="ltr"
                pattern="#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})"
                spellCheck={false}
                autoComplete="off"
                error={result.status === 'rejected' ? t(`reject.${result.code}`) : undefined}
              />
            </div>
            <TextField
              id={logoId}
              type="file"
              accept="image/png,image/jpeg"
              label={t('logo.label')}
              hint={t('logo.hint')}
              error={logoError ? t(`logo.${logoError}`) : undefined}
              onChange={(e) => onLogo(e.target.files?.[0])}
              disabled={!editable}
            />
            {logo ? <Alert tone="info">{t('logo.pending', { name: plainText(logo.fileName, 80) })}</Alert> : null}
          </Stack>
        </Card>
        <div id="branding-preview">
          {result.status === 'ok' ? (
            <Stack>
              <h2>{t('preview.title')}</h2>
              {panel('light', result.light, result.adjusted.light)}
              {panel('dark', result.dark, result.adjusted.dark)}
            </Stack>
          ) : (
            <Alert tone="warning" role="presentation" title={t('result.rejected')}>
              {t(`reject.${result.code}`)}
            </Alert>
          )}
          {result.status === 'rejected' && raw ? failedList(raw) : null}
        </div>
      </div>
      {result.status === 'ok' ? (
        <Card as="section" aria-labelledby="branding-contrast">
          <h2 id="branding-contrast">{t('result.title')}</h2>
          <p>{tr('result.ok', { adjusted: result.adjusted.light ? 'yes' : 'no' })}</p>
          <p>{t('result.note')}</p>
          {table('light', result.light.pairs, raw?.light)}
          {table('dark', result.dark.pairs, raw?.dark)}
        </Card>
      ) : null}
      <VisuallyHidden role="status">
        {result.status === 'ok' ? t('result.statusOk') : t(`reject.${result.code}`)}
      </VisuallyHidden>
      {loaded === 'loading' ? <Alert tone="info">{t('loading')}</Alert> : null}
      {loaded === 'failed' ? <Alert tone="danger">{t('loadFailed')}</Alert> : null}
      <div className={styles.actions}>
        <Button onClick={onSave} loading={status === 'saving'} disabled={!valid || !editable}>
          {status === 'saving' ? t('saving') : t('save')}
        </Button>
        {loaded === 'ready' && !valid ? <span>{t('fixBeforeSave')}</span> : null}
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
