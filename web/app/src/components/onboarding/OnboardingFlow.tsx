'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { Button, Card, Icon, Mark, VisuallyHidden } from '../../ui';
import { back, canGoBack, initialOnboarding, isLast, next, onboardingSteps, stepOf, type OnboardingState } from '../../lib/onboarding';
import { ProgressMarks } from '../marks/ProgressMarks';
import { cx } from '../../ui/cx';
import button from '../../ui/Button.module.css';
import styles from './Onboarding.module.css';

export type OnboardingFlowProps = {
  /** Starting state, for tests and previews only. */
  initial?: OnboardingState;
};

/**
 * The owner's first run (WEB-012, design WEB-029): the five-stage journey at the top (the owner is at Discover), a step list
 * beside one calm card per step, and the promise that nothing goes live without approval. The model is pure (lib/onboarding).
 */
export function OnboardingFlow({ initial = initialOnboarding }: OnboardingFlowProps) {
  const t = useTranslations('onboarding');
  const tp = useTranslations('marks.progress');
  const [state, setState] = useState<OnboardingState>(initial);
  const step = stepOf(state);
  const current = onboardingSteps.indexOf(step);
  const total = onboardingSteps.length;
  const points = t.raw(`steps.${step}.points`) as string[];

  return (
    <section className={styles.page} aria-labelledby="onboarding-title">
      <header className={styles.band}>
        <p className={styles.eyebrow}>
          <Mark size={16} />
          {t('eyebrow')}
        </p>
        <div className={styles.journey}>
          <p className={styles.journeyLabel}>{t('journeyLabel')}</p>
          <ProgressMarks buildState={null} size={20} />
        </div>
      </header>

      <div className={styles.layout}>
        <ol role="list" className={styles.steps} aria-label={t('stepsLabel')}>
          {onboardingSteps.map((id, i) => {
            const s = i < current ? 'done' : i === current ? 'current' : 'upcoming';
            return (
              <li key={id} data-step={id} data-state={s} className={styles.stepItem} aria-current={s === 'current' ? 'step' : undefined}>
                <span className={styles.stepMark} aria-hidden="true">
                  {s === 'done' ? <Icon name="statusDone" /> : <span className={styles.stepNum}>{i + 1}</span>}
                </span>
                <span className={styles.stepTitle}>{t(`steps.${id}.title`)}</span>
                <VisuallyHidden>{tp(`state.${s}`)}</VisuallyHidden>
              </li>
            );
          })}
        </ol>

        <Card className={styles.card}>
          <div className={styles.meter} aria-hidden="true">
            {onboardingSteps.map((id, i) => (
              <span key={id} className={styles.segment} data-on={i <= current ? 'true' : undefined} />
            ))}
          </div>
          <p className={styles.progress} aria-live="polite">
            {t('progress', { current: state.index + 1, total })}
          </p>
          <h1 id="onboarding-title" className={styles.title}>
            {t(`steps.${step}.title`)}
          </h1>
          <p className={styles.body}>{t(`steps.${step}.body`)}</p>
          <ul role="list" className={styles.points}>
            {points.map((p) => (
              <li key={p} className={styles.point}>
                <Mark size={16} className={styles.bullet} />
                <span>{p}</span>
              </li>
            ))}
          </ul>
          <div className={styles.actions}>
            {canGoBack(state) ? (
              <Button variant="secondary" size="lg" onClick={() => setState(back(state))}>
                {t('back')}
              </Button>
            ) : null}
            {isLast(state) ? (
              <Link className={cx(button.root, button.primary, button.lg, styles.forward)} href="/chat/">
                <Icon name="chat" />
                {t('start')}
              </Link>
            ) : (
              <Button size="lg" className={styles.forward} onClick={() => setState(next(state))}>
                {t('next')}
              </Button>
            )}
          </div>
          <div className={styles.foot}>
            <p className={styles.reassure}>
              <Icon name="lock" />
              {t('reassure')}
            </p>
            {!isLast(state) ? (
              <Link className={styles.skip} href="/chat/">
                {t('skip')}
              </Link>
            ) : null}
          </div>
        </Card>
      </div>
    </section>
  );
}
