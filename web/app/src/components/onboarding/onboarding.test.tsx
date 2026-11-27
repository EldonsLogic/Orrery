import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import { messages, type Locale } from '../../i18n';
import { OnboardingFlow } from './OnboardingFlow';
import { back, canGoBack, initialOnboarding, isLast, next, onboardingSteps, stepOf } from '../../lib/onboarding';

const render = (locale: Locale, index: number) =>
  renderToString(
    <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone="UTC">
      <OnboardingFlow initial={{ index }} />
    </NextIntlClientProvider>,
  );

describe('onboarding model', () => {
  it('starts on the first step and cannot go back', () => {
    expect(stepOf(initialOnboarding)).toBe('welcome');
    expect(canGoBack(initialOnboarding)).toBe(false);
    expect(back(initialOnboarding)).toEqual(initialOnboarding);
  });
  it('walks forward to the last step and stops there', () => {
    let s = initialOnboarding;
    for (let i = 0; i < 20; i++) s = next(s);
    expect(stepOf(s)).toBe(onboardingSteps[onboardingSteps.length - 1]);
    expect(isLast(s)).toBe(true);
    expect(next(s)).toEqual(s);
  });
  it('clamps an out-of-range index', () => {
    expect(stepOf({ index: -5 })).toBe('welcome');
    expect(stepOf({ index: 99 })).toBe('ready');
  });
});

describe.each(['en', 'ar'] as const)('onboarding screens in %s', (locale) => {
  const m = messages[locale].onboarding;
  it('has text for every step', () => {
    for (const id of onboardingSteps) {
      expect(m.steps[id].title.length).toBeGreaterThan(0);
      expect(m.steps[id].points.length).toBeGreaterThan(0);
    }
  });
  it('first step: title, next and skip, no back', () => {
    const out = render(locale, 0);
    expect(out).toContain(m.steps.welcome.title);
    expect(out).toContain(m.next);
    expect(out).toContain(m.skip);
    expect(out).not.toContain(`>${m.back}<`);
    expect(out).toContain('aria-labelledby="onboarding-title"');
  });
  it('shows the five-stage journey with Discover current, and says nothing goes live without approval', () => {
    const out = render(locale, 0);
    const marks = messages[locale].marks.progress;
    expect(out).toContain(`aria-label="${marks.title}"`);
    expect(out).toContain(marks.stage.discover);
    expect(out).toContain(marks.stage.live);
    expect(out).toContain(m.reassure);
  });
  it('lists every step and marks the current one', () => {
    const out = render(locale, 2);
    for (const id of onboardingSteps) expect(out).toContain(m.steps[id].title);
    expect(out).toContain('data-step="documents" data-state="current"');
    expect(out).toContain('data-step="welcome" data-state="done"');
    expect(out).toContain('data-step="ready" data-state="upcoming"');
  });
  it('middle step shows back', () => {
    expect(render(locale, 2)).toContain(m.back);
  });
  it('last step links to the chat and has no next', () => {
    const out = render(locale, onboardingSteps.length - 1);
    expect(out).toMatch(/href="\/chat\/?"/);
    expect(out).toContain(m.start);
    expect(out).not.toContain(`>${m.next}<`);
  });
});
