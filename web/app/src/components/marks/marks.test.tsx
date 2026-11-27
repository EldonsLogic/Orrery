// BRD-014: brand state marks (kit "Extending the system", guidelines p.10). Server-rendered, no jsdom.
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { NextIntlClientProvider } from 'next-intl';
import type { ReactElement } from 'react';
import { messages, type Locale } from '../../i18n';
import { Mark } from '../../ui';
import { BUILD_STAGES, stageProgress } from '../../lib/buildProgress';
import { StatusMark, STATUS_MARKS } from './StatusMark';
import { ProgressMarks } from './ProgressMarks';
import { LoadingMark } from './LoadingMark';

const render = (node: ReactElement, locale: Locale = 'en') =>
  renderToString(
    <div dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]}>
        {node}
      </NextIntlClientProvider>
    </div>,
  );
const fills = (html: string) => [...html.matchAll(/data-half="(upper|lower)" data-fill="(solid|outline)"/g)].map((m) => `${m[1]}:${m[2]}`);
// Comments are stripped so a rule may name what it forbids.
const css = (rel: string) => readFileSync(join(__dirname, rel), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
const MOTION = /transform|rotate|scale|translate|matrix|skew/i;

describe('Mark', () => {
  it('renders the two halves of the master cut, each solid or outline', () => {
    const out = renderToString(<Mark upper="solid" lower="outline" size={32} />);
    expect(fills(out)).toEqual(['upper:solid', 'lower:outline']);
    expect(out).toContain('data-cut="master"');
    expect(out).toContain('M40.82 103.18');
    expect(out).toContain('M215.18 152.82');
    expect(out).toContain('aria-hidden="true"');
  });
  it('switches to the small-size cut below 24 px', () => {
    expect(renderToString(<Mark size={23} />)).toContain('data-cut="small"');
    expect(renderToString(<Mark size={16} />)).toContain('M32.32 103.68');
    expect(renderToString(<Mark size={24} />)).toContain('data-cut="master"');
  });
  it('takes colour from tokens only and never transforms', () => {
    const out = renderToString(<Mark tone="accent" />);
    expect(out).toContain('currentColor');
    expect(out).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(out).not.toMatch(MOTION);
    const sheet = css('../../ui/Mark.module.css');
    expect(sheet).toContain('var(--seshna-mark)');
    expect(sheet).toContain('var(--seshna-mark-accent)');
    expect(sheet).not.toContain('--color-');
    expect(sheet).not.toMatch(MOTION);
  });
});

describe('Mark colour under a tenant theme (founders, 2026-11-24)', () => {
  const brand = join(__dirname, '../../../../../docs/brand/tokens');
  const tokens = JSON.parse(readFileSync(join(brand, 'tokens.json'), 'utf8'));
  const base = readFileSync(join(brand, 'tokens.css'), 'utf8');
  const mark = tokens.brandMark;
  // A tenant override block in the shape derive_tenant_theme.py writes (layer 2, loaded after the base tokens),
  // with colours that are not Cobalt or Coral (Jade and Ochre stand in for a tenant's brand).
  const tenant = `:root[data-tenant="acme"] {\n  --color-primary: ${tokens.color.light.success.hex};\n  --color-accent: ${tokens.color.light.warning.hex};\n}\n`;
  const decls = (text: string) => Object.fromEntries([...text.matchAll(/(--[a-z0-9-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2]!.trim()]));
  const resolve = (value: string, vars: Record<string, string>): string => {
    const m = /^var\((--[a-z0-9-]+)\)$/.exec(value);
    return m ? resolve(vars[m[1]!] ?? '', vars) : value;
  };
  it('keeps Seshna Cobalt and Coral when a tenant overrides the primary and accent', () => {
    const vars = { ...decls(base.slice(0, base.indexOf('@media'))), ...decls(tenant) };
    const sheet = css('../../ui/Mark.module.css');
    const colours = [...sheet.matchAll(/(?:^|\s)color:\s*([^;]+);/g)].map((m) => resolve(m[1]!.trim(), vars));
    expect(colours).toEqual([mark.light.mark.hex, mark.light.markAccent.hex]);
    expect(resolve('var(--color-primary)', vars)).toBe(tokens.color.light.success.hex);
    expect(Object.keys(decls(tenant)).some((k) => k.startsWith('--seshna-'))).toBe(false);
  });
  it('uses exactly the palette Cobalt and Coral in both themes', () => {
    for (const m of ['light', 'dark'] as const) {
      expect(mark[m].mark.hex).toBe(tokens.color[m].primary.hex);
      expect(mark[m].markAccent.hex).toBe(tokens.color[m].accent.hex);
    }
  });
  it('has dark values for the mark tokens in both dark blocks', () => {
    expect(base.split(`--seshna-mark: ${mark.dark.mark.hex};`)).toHaveLength(3);
    expect(base.split(`--seshna-mark-accent: ${mark.dark.markAccent.hex};`)).toHaveLength(3);
  });
});

describe('StatusMark', () => {
  it.each([
    ['not_started', ['upper:outline', 'lower:outline']],
    ['drafted', ['upper:solid', 'lower:outline']],
    ['approved', ['upper:solid', 'lower:solid']],
  ] as const)('%s has the right halves and a visible word in both languages', (status, halves) => {
    for (const locale of ['en', 'ar'] as const) {
      const out = render(<StatusMark status={status} />, locale);
      expect(fills(out)).toEqual(halves);
      expect(out).toContain(messages[locale].marks.status[status]);
      expect(out).toContain(`data-status="${status}"`);
    }
  });
  it('covers every status', () => {
    expect([...STATUS_MARKS]).toEqual(['not_started', 'drafted', 'approved']);
  });
});

describe('stageProgress', () => {
  it('maps the build state machine (BPL-020) to the five stages', () => {
    expect(BUILD_STAGES).toEqual(['discover', 'blueprint', 'build', 'simulate', 'live']);
    expect(stageProgress(undefined)).toBe(0);
    expect(stageProgress('unknown')).toBe(0);
    expect(stageProgress('draft')).toBe(1);
    expect(stageProgress('owner_approved')).toBe(2);
    expect(stageProgress('team_reviewed')).toBe(2);
    expect(stageProgress('built_in_sandbox')).toBe(3);
    expect(stageProgress('simulated')).toBe(4);
    expect(stageProgress('live')).toBe(5);
  });
});

describe('ProgressMarks', () => {
  it('marks done stages solid, the current one half and upcoming ones outline (guidelines p.10)', () => {
    const out = render(<ProgressMarks buildState="owner_approved" />);
    expect(fills(out)).toEqual([
      'upper:solid', 'lower:solid',
      'upper:solid', 'lower:solid',
      'upper:solid', 'lower:outline',
      'upper:outline', 'lower:outline',
      'upper:outline', 'lower:outline',
    ]);
    expect(out.match(/aria-current="step"/g)).toHaveLength(1);
    expect(out).toContain('<ol role="list"');
    for (const s of BUILD_STAGES) expect(out).toContain(messages.en.marks.progress.stage[s]);
    expect(out).toContain(messages.en.marks.progress.state.current);
  });
  it('shows every stage solid once live, with no current step', () => {
    const out = render(<ProgressMarks buildState="live" />, 'ar');
    expect(fills(out).every((f) => f.endsWith('solid'))).toBe(true);
    expect(out).not.toContain('aria-current');
    for (const s of BUILD_STAGES) expect(out).toContain(messages.ar.marks.progress.stage[s]);
  });
  it('is not mirrored in RTL: same geometry, no transform', () => {
    const ltr = render(<ProgressMarks buildState="draft" />, 'en');
    const rtl = render(<ProgressMarks buildState="draft" />, 'ar');
    const paths = (h: string) => [...h.matchAll(/ d="([^"]+)"/g)].map((m) => m[1]);
    expect(paths(rtl)).toEqual(paths(ltr));
    expect(rtl).not.toMatch(MOTION);
  });
  it('shows a visible status word under every step (WEB-029)', () => {
    const out = render(<ProgressMarks buildState="built_in_sandbox" />);
    const words = [...out.matchAll(/class="_stageState_[^"]*">([^<]+)</g)].map((m) => m[1]);
    const s = messages.en.marks.progress.state;
    expect(words).toEqual([s.done, s.done, s.done, s.current, s.upcoming]);
  });
  it('never breaks a stage name mid-word; narrow containers stack the stages as a vertical list (WEB-029 N2)', () => {
    const sheet = css('Marks.module.css');
    expect(sheet).not.toMatch(/overflow-wrap:\s*anywhere|word-break:\s*break-all/);
    expect(sheet).toMatch(/\.progress \{[^}]*container-type: inline-size[^}]*flex-wrap: wrap/);
    const at = sheet.indexOf('@container (inline-size < 28rem)');
    expect(at).toBeGreaterThan(-1);
    const narrow = sheet.slice(at);
    expect(narrow).toMatch(/\.stage \{[^}]*flex-basis: 100%[^}]*flex-direction: row/);
    expect(narrow).toMatch(/\.stage \+ \.stage::before \{[^}]*border-inline-start: [^;]*solid var\(--color-primary\)/);
    expect(narrow).toMatch(/\.stage\[data-state='upcoming'\]::before \{[^}]*border-inline-start-style: dashed/);
  });
  it('connects the steps: solid primary up to the current step, dashed and muted after it, on logical insets', () => {
    const sheet = css('Marks.module.css');
    expect(sheet).toMatch(/\.stage \+ \.stage::before \{[^}]*inset-inline-start[^}]*border-block-start: [^;]*solid var\(--color-primary\)/);
    expect(sheet).toMatch(/\.stage\[data-state='upcoming'\]::before \{[^}]*dashed[^}]*var\(--color-border-control\)/);
  });
});

describe('LoadingMark', () => {
  it('is a live status with a visible text label', () => {
    const out = render(<LoadingMark label="Working" />);
    expect(out).toContain('role="status"');
    expect(out).toContain('Working');
    expect(out).toContain('data-loading="true"');
  });
  it('falls back to the default label in both languages', () => {
    expect(render(<LoadingMark />, 'en')).toContain(messages.en.marks.loading);
    expect(render(<LoadingMark />, 'ar')).toContain(messages.ar.marks.loading);
  });
  it('cycles fill only, never rotates, scales or moves the halves', () => {
    const sheet = css('Marks.module.css');
    expect(sheet).toMatch(/@keyframes/);
    expect(sheet).toContain('fill-opacity');
    expect(sheet).not.toMatch(MOTION);
  });
  it('shows the static drafted state under prefers-reduced-motion', () => {
    const sheet = css('Marks.module.css');
    const reduced = sheet.slice(sheet.indexOf('@media (prefers-reduced-motion: reduce)'));
    expect(reduced.length).toBeGreaterThan(0);
    expect(reduced).toContain('animation: none');
    expect(reduced).toMatch(/\[data-half='upper'\][^}]*fill-opacity: 1/);
    expect(reduced).toMatch(/\[data-half='lower'\][^}]*fill-opacity: 0/);
  });
});

describe('i18n', () => {
  it('has every mark key in en and ar', () => {
    for (const locale of ['en', 'ar'] as const) {
      const m = messages[locale].marks;
      for (const s of STATUS_MARKS) expect(m.status[s]).toBeTruthy();
      for (const s of BUILD_STAGES) expect(m.progress.stage[s]).toBeTruthy();
      for (const s of ['done', 'current', 'upcoming'] as const) expect(m.progress.state[s]).toBeTruthy();
      expect(m.progress.title).toBeTruthy();
      expect(m.loading).toBeTruthy();
    }
  });
});
