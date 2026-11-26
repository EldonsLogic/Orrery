'use client';

import type { CSSProperties } from 'react';
import { useTranslations } from 'next-intl';
import { Mark, type MarkFill } from '../../ui';
import { BUILD_STAGES, stageProgress } from '../../lib/buildProgress';
import styles from './Marks.module.css';

/**
 * The five build stages: the Nuqta S fills up across the journey (Eldon 2026-11-26). The fill is fixed per step and
 * shows the journey's shape: Discover outline, Blueprint upper half tinted, Build upper solid, Simulate upper solid
 * and lower tinted, Live both solid. Progress is shown separately: steps after the current one are muted. The list
 * follows the reading direction; the marks never mirror.
 */
const STEP_FILL: ReadonlyArray<readonly [MarkFill, MarkFill]> = [
  ['outline', 'outline'],
  ['tint', 'outline'],
  ['solid', 'outline'],
  ['solid', 'tint'],
  ['solid', 'solid'],
];

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
            <Mark upper={STEP_FILL[i][0]} lower={STEP_FILL[i][1]} size={size} />
            <span>{t(`stage.${stage}`)}</span>
            <span className={styles.stageState}>{t(`state.${state}`)}</span>
          </li>
        );
      })}
    </ol>
  );
}
