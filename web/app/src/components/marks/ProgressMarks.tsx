'use client';

import type { CSSProperties } from 'react';
import { useTranslations } from 'next-intl';
import { Mark } from '../../ui';
import { BUILD_STAGES, stageProgress } from '../../lib/buildProgress';
import styles from './Marks.module.css';

/**
 * The five build stages (brand kit "Progress"): completed stages solid, the current stage half (upper solid,
 * lower outline), upcoming stages outline. The list follows the reading direction; the marks never mirror.
 */
export function ProgressMarks({ buildState, size = 24 }: { buildState: string | null | undefined; size?: number }) {
  const t = useTranslations('marks.progress');
  const current = stageProgress(buildState);
  return (
    // role="list": list-style none drops list semantics in Safari and VoiceOver.
    <ol role="list" className={styles.progress} aria-label={t('title')} style={{ '--progress-mark': `${size}px` } as CSSProperties}>
      {BUILD_STAGES.map((stage, i) => {
        const state = i < current ? 'done' : i === current ? 'current' : 'upcoming';
        return (
          <li key={stage} className={styles.stage} data-state={state} aria-current={state === 'current' ? 'step' : undefined}>
            <Mark upper={state === 'upcoming' ? 'outline' : 'solid'} lower={state === 'done' ? 'solid' : 'outline'} size={size} />
            <span>{t(`stage.${stage}`)}</span>
            <span className={styles.stageState}>{t(`state.${state}`)}</span>
          </li>
        );
      })}
    </ol>
  );
}
