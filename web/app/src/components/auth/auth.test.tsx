import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import { messages, type Locale } from '../../i18n';
import { LoginForm } from './LoginForm';
import { ResetRequestForm } from './ResetRequestForm';
import { ResetConfirmForm } from './ResetConfirmForm';
import { ErrorView } from './ErrorView';
import { placeholderLogin, placeholderResetRequest } from '../../lib/authPlaceholder';

const render = (locale: Locale, node: ReactElement) =>
  renderToString(
    <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone="UTC">
      {node}
    </NextIntlClientProvider>,
  );

const dirOf = { en: 'dir="ltr"', ar: 'dir="rtl"' } as const;
const locales: Locale[] = ['en', 'ar'];

describe.each(locales)('auth pages in %s', (locale) => {
  const m = messages[locale];

  it('login: dir, linked labels, autocomplete, forgot link', () => {
    const out = render(locale, <LoginForm />);
    expect(out).toContain(dirOf[locale]);
    expect(out).toContain(m.auth.login.title);
    expect(out).toContain(m.auth.login.forgot);
    expect(out).toContain('autoComplete="username"');
    expect(out).toContain('autoComplete="current-password"');
    expect(out.match(/<label for="/g)).toHaveLength(2);
    expect(out).not.toContain('role="alert"');
  });

  it('login failure shows a generic alert', () => {
    const out = render(locale, <LoginForm initialResult={{ ok: false }} />);
    expect(out).toContain('role="alert"');
    expect(out).toContain(m.auth.login.error);
  });

  it('reset request: label, sent state', () => {
    const out = render(locale, <ResetRequestForm />);
    expect(out).toContain(dirOf[locale]);
    expect(out.match(/<label for="/g)).toHaveLength(1);
    expect(render(locale, <ResetRequestForm initialResult={{ ok: true }} />)).toContain(m.auth.reset.sent);
    expect(render(locale, <ResetRequestForm initialResult={{ ok: false }} />)).toContain('role="alert"');
  });

  it('reset confirm: two new-password fields, states', () => {
    const out = render(locale, <ResetConfirmForm />);
    expect(out).toContain(dirOf[locale]);
    expect(out.match(/autoComplete="new-password"/g)).toHaveLength(2);
    expect(out.match(/<label for="/g)).toHaveLength(2);
    expect(render(locale, <ResetConfirmForm initialResult={{ ok: false }} />)).toContain(m.auth.confirm.error);
    expect(render(locale, <ResetConfirmForm initialResult={{ ok: true }} />)).toContain(m.auth.confirm.done);
  });

  it.each(['notFound', 'generic', 'global'] as const)('error view %s has dir and text', (kind) => {
    const out = render(locale, <ErrorView kind={kind} onRetry={() => {}} />);
    expect(out).toContain(dirOf[locale]);
    expect(out).toContain(m.errors[kind].title);
    expect(out).toContain(m.errors.retry);
  });

  it('never mentions the engine and uses no hard-coded colours', () => {
    const all = JSON.stringify(m) + render(locale, <LoginForm />);
    expect(all).not.toMatch(new RegExp(['fra' + 'ppe', 'erp' + 'next'].join('|'), 'i'));
    expect(all).not.toMatch(/#[0-9a-fA-F]{6}/);
  });
});

describe('placeholder handlers', () => {
  it('return fixed results', async () => {
    expect(await placeholderLogin({ email: 'a@b.c', password: 'x' })).toEqual({ ok: false });
    expect(await placeholderResetRequest({ email: 'a@b.c' })).toEqual({ ok: true });
  });
});
