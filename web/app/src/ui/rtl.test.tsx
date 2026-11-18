// QA-008: deterministic RTL layout checks (no screenshot baselines; images cannot be committed).
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import { createThemeEngine } from '../../theme/theme-engine.js';
import { directionOf, messages, type Locale } from '../i18n';
import { LoginForm } from '../components/auth/LoginForm';
import { ResetRequestForm } from '../components/auth/ResetRequestForm';
import { ResetConfirmForm } from '../components/auth/ResetConfirmForm';
import { Alert, Badge, Button, Card, Checkbox, Select, Spinner, Stack, Table, TextField } from './index';

const dirs = ['rtl', 'ltr'] as const;

const sample = (
  <Stack gap={2}>
    <Alert tone="danger">Alert</Alert>
    <Badge>Badge</Badge>
    <Button>Go</Button>
    <Card>Card</Card>
    <Checkbox id="c" label="Check" />
    <Select id="s" label="Select">
      <option value="a">A</option>
    </Select>
    <Spinner label="Loading" />
    <TextField id="t" label="Text" />
    <TextField id="n" label="Amount" numeric />
    <Table caption="T" rows={[{ id: 'a', total: 5 }]} rowKey={(r) => r.id} columns={[{ key: 'id', header: 'No.' }, { key: 'total', header: 'Total', numeric: true }]} />
  </Stack>
);

const withDir = (dir: 'rtl' | 'ltr', node: ReactElement) => renderToString(<div dir={dir}>{node}</div>);
const inlineStyles = (out: string) => [...out.matchAll(/style="([^"]*)"/g)].map((m) => m[1]);

describe.each(dirs)('ui components in dir=%s', (dir) => {
  const out = withDir(dir, sample);
  it('keeps the root dir attribute', () => {
    expect(out.startsWith(`<div dir="${dir}"`)).toBe(true);
    // The only nested dir values are the numeric field (ltr) and auto text fields.
    const nested = [...out.matchAll(/dir="(\w+)"/g)].map((m) => m[1]).slice(1);
    expect(new Set(nested)).toEqual(new Set(['auto', 'ltr']));
  });
  it('uses no physical left/right in inline styles', () => {
    for (const s of inlineStyles(out)) expect(s).not.toMatch(/(?:^|[;\s-])(?:left|right)\s*:|(?:margin|padding|border)-(?:left|right)/i);
  });
  it('does not set text-align or float inline', () => {
    for (const s of inlineStyles(out)) expect(s).not.toMatch(/text-align|float/i);
  });
  it('numeric inputs stay LTR for digits in either direction; text inputs follow the content', () => {
    expect(out).toContain('dir="ltr"');
    expect(out).toContain('dir="auto"');
  });
  it('numeric table cells align to the logical end, not a physical side', () => {
    const css = readFileSync(join(__dirname, 'Table.module.css'), 'utf8');
    expect(css).toMatch(/\.numeric\s*\{[^}]*text-align:\s*end/);
    expect(out).not.toMatch(/class="[^"]*(?:\bleft\b|\bright\b)/);
  });
});

const render = (locale: Locale, node: ReactElement) =>
  renderToString(
    <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone="UTC">
      {node}
    </NextIntlClientProvider>,
  );

describe.each([['ar', 'rtl'], ['en', 'ltr']] as const)('auth forms in %s', (locale, dir) => {
  it.each([
    ['login', <LoginForm key="l" />],
    ['reset request', <ResetRequestForm key="r" />],
    ['reset confirm', <ResetConfirmForm key="c" />],
  ])('%s: root dir follows the locale and no inline physical styles', (_n, node) => {
    expect(directionOf(locale)).toBe(dir);
    const out = render(locale, node);
    expect(out).toContain(`dir="${dir}"`);
    expect(out).toContain(`lang="${locale}"`);
    for (const s of inlineStyles(out)) expect(s).not.toMatch(/(?:^|[;\s-])(?:left|right)\s*:/i);
  });
});

describe('tenant theme overrides never change direction', () => {
  const fakeRoot = () => {
    const attrs = new Map<string, string>([['dir', 'rtl']]);
    return {
      attrs,
      style: {} as Record<string, string>,
      setAttribute: (k: string, v: string) => void attrs.set(k, v),
      removeAttribute: (k: string) => void attrs.delete(k),
    };
  };
  const store = () => {
    const m = new Map<string, string>();
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
  };
  it.each(['light', 'dark', 'system'])('mode %s leaves dir untouched for two tenants', (mode) => {
    for (const tenantId of ['tenant-a', 'tenant-b']) {
      const root = fakeRoot();
      const engine = createThemeEngine({ root, storage: store(), matchMedia: () => ({ matches: false }), tenantId, userId: 'u1' });
      engine.set(mode);
      expect(root.attrs.get('dir')).toBe('rtl');
      expect([...root.attrs.keys()].filter((k) => k !== 'dir' && k !== 'data-theme')).toEqual([]);
      expect(Object.keys(root.style).filter((k) => /direction|writing/i.test(k))).toEqual([]);
    }
  });
});
