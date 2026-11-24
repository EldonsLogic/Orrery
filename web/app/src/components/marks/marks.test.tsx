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
    expect(sheet).toContain('var(--color-primary)');
    expect(sheet).toContain('var(--color-accent)');
    expect(sheet).not.toMatch(MOTION);
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
    expect(out).toContain('<ol');
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
