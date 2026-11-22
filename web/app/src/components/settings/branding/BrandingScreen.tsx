'use client';

import { useEffect, useId, useMemo, useState, type CSSProperties } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Alert, Button, Card, Stack, TextField } from '../../../ui';
import { canEditBranding } from '../../../settings/branding/access';
import { DEFAULT_PRIMARY, derive, normHex, rawPairs, type Pair, type Theme } from '../../../settings/branding/colour';
import { checkLogo, createFakeBrandingPort, type BrandingPort, type BrandingSettings } from '../../../settings/branding/port';
import { fixtureBlueprint } from '../../../blueprint/fixture';
import { callerOf } from '../../../lib/session';
import { useSession } from '../../shell/SessionProvider';
import styles from './BrandingScreen.module.css';

type Translate = (key: string, values?: Record<string, string | number>) => string;
type Status = 'idle' | 'saving' | 'saved' | 'forbidden' | 'invalid' | 'failed';

/** Settings > Branding (WEB-007). The session decides who may edit; the data comes from a fake port until the gateway exists. */
export function BrandingScreen({ port }: { port?: BrandingPort }) {
  const { session } = useSession();
  const t = useTranslations('branding');
  const fallback = useMemo(() => createFakeBrandingPort(), []);
  if (session.status !== 'ready') return null;
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
  return <BrandingEditor port={port ?? fallback} initial={null} />;
}

export function BrandingEditor({ port, initial }: { port: BrandingPort; initial: BrandingSettings | null }) {
  const t = useTranslations('branding');
  const tr = t as unknown as Translate;
  const locale = useLocale();
  const nf = useMemo(() => new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 }), [locale]);
  const [text, setText] = useState(initial?.primary ?? DEFAULT_PRIMARY);
  const [logo, setLogo] = useState<BrandingSettings['logo']>(initial?.logo ?? null);
  const [logoError, setLogoError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>('idle');
  const logoId = useId();

  useEffect(() => {
    if (initial) return;
    let live = true;
    void port.load().then((s) => {
      if (live) {
        setText(s.primary);
        setLogo(s.logo);
      }
    });
    return () => {
      live = false;
    };
  }, [port, initial]);

  const result = useMemo(() => derive(text), [text]);
  const raw = useMemo(() => rawPairs(text), [text]);
  const valid = result.status === 'ok';
  const picked = normHex(text);

  const onSave = async () => {
    if (!picked || !valid) return;
    setStatus('saving');
    const r = await port.save({ primary: picked, logo });
    setStatus(r.ok ? 'saved' : r.code);
  };

  // Only the file's name, type and size are read; its bytes are never opened, rendered or previewed (SEC-006 not built).
  const onLogo = async (file: File | undefined) => {
    if (!file) return;
    setLogoError(null);
    const bad = checkLogo({ fileName: file.name, mediaType: file.type, sizeBytes: file.size });
    if (bad) return setLogoError(bad === 'type' ? 'errType' : 'errSize');
    const r = await port.uploadLogo({ fileName: file.name, mediaType: file.type, sizeBytes: file.size });
    if (r.ok) setLogo(r.logo);
    else setLogoError(r.code === 'type' ? 'errType' : r.code === 'size' ? 'errSize' : 'errFailed');
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
          <a className={styles.pLink} href="#branding-preview" onClick={(e) => e.preventDefault()}>
            {t('preview.link')}
          </a>
          <span className={styles.pBtn}>{t('preview.button')}</span>
        </div>
        <span>
          <span className={styles.swatch} style={{ background: theme.primary }} aria-hidden="true" /> <bdi dir="ltr">{theme.primary}</bdi>
        </span>
        {adjusted ? <small>{tr('preview.adjusted', { colour: theme.primary })}</small> : null}
      </div>
    );
  };
  const table = (mode: 'light' | 'dark', pairs: ReadonlyArray<Pair>, rawPairsOfMode: ReadonlyArray<Pair> | undefined) => (
    <table key={mode} className={styles.pairs}>
      <caption>
        {tr('result.summary', { pass: pairs.filter((p) => p.ok).length, total: pairs.length, theme: t(`themeName.${mode}`) })}
        {rawPairsOfMode ? ` (${t('result.raw')}: ${rawPairsOfMode.filter((p) => p.ok).length}/${rawPairsOfMode.length})` : ''}
      </caption>
      <thead>
        <tr>
          <th scope="col">{t('result.pair')}</th>
          <th scope="col">{t('result.ratio')}</th>
          <th scope="col">{t('result.min')}</th>
          <th scope="col">{t('result.pass')}</th>
        </tr>
      </thead>
      <tbody>
        {pairs.map((p) => (
          <tr key={p.id}>
            <th scope="row">{pairLabel(p.id)}</th>
            <td className={styles.num}>{nf.format(p.ratio)}:1</td>
            <td className={styles.num}>{nf.format(p.min)}:1</td>
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
        <Card as="section" aria-label={t('colour.label')}>
          <Stack>
            <div className={styles.row}>
              <input
                type="color"
                className={styles.picker}
                aria-label={t('colour.picker')}
                value={(picked ?? DEFAULT_PRIMARY).toLowerCase()}
                onChange={(e) => setText(e.target.value.toUpperCase())}
              />
              <TextField
                label={t('colour.label')}
                hint={t('colour.hint')}
                value={text}
                onChange={(e) => setText(e.target.value)}
                numeric
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
              onChange={(e) => void onLogo(e.target.files?.[0])}
            />
            {logo ? <Alert tone="info">{t('logo.pending', { name: logo.fileName })}</Alert> : null}
          </Stack>
        </Card>
        <div id="branding-preview" aria-live="polite">
          {result.status === 'ok' ? (
            <Stack>
              <h2>{t('preview.title')}</h2>
              {panel('light', result.light, result.adjusted.light)}
              {panel('dark', result.dark, result.adjusted.dark)}
            </Stack>
          ) : (
            <Alert tone="warning" title={t('result.rejected')}>
              {t(`reject.${result.code}`)}
            </Alert>
          )}
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
      <div className={styles.actions}>
        <Button onClick={() => void onSave()} loading={status === 'saving'} disabled={!valid}>
          {status === 'saving' ? t('saving') : t('save')}
        </Button>
        {!valid ? <span>{t('fixBeforeSave')}</span> : null}
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
