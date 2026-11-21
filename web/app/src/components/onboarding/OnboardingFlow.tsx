'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Button, Card, Stack } from '../../ui';
import { back, canGoBack, initialOnboarding, isLast, next, onboardingSteps, stepOf, type OnboardingState } from '../../lib/onboarding';
import styles from './Onboarding.module.css';

export type OnboardingFlowProps = {
  /** Starting state, for tests and previews only. */
  initial?: OnboardingState;
};

/** Five short screens that explain the first run: the chat interview, documents, review, then start. */
export function OnboardingFlow({ initial = initialOnboarding }: OnboardingFlowProps) {
  const t = useTranslations('onboarding');
  const [state, setState] = useState<OnboardingState>(initial);
  const step = stepOf(state);
  const total = onboardingSteps.length;
  const points = t.raw(`steps.${step}.points`) as string[];

  return (
    <section className={styles.root} aria-labelledby="onboarding-title">
      <Card>
        <Stack gap={2}>
          <p className={styles.progress} aria-live="polite">
            {t('progress', { current: state.index + 1, total })}
          </p>
          <h1 id="onboarding-title" className={styles.title}>
            {t(`steps.${step}.title`)}
          </h1>
          <p className={styles.body}>{t(`steps.${step}.body`)}</p>
          <ul className={styles.points}>
            {points.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
          <Stack direction="row" gap={1} wrap>
            {canGoBack(state) ? (
              <Button variant="secondary" onClick={() => setState(back(state))}>
                {t('back')}
              </Button>
            ) : null}
            {isLast(state) ? (
              <Link className={styles.start} href="/chat/">
                {t('start')}
              </Link>
            ) : (
              <Button onClick={() => setState(next(state))}>{t('next')}</Button>
            )}
          </Stack>
          {!isLast(state) ? (
            <Link className={styles.skip} href="/chat/">
              {t('skip')}
            </Link>
          ) : null}
        </Stack>
      </Card>
    </section>
  );
}
