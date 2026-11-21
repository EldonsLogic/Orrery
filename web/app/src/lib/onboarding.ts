// First-run onboarding model (WEB-012). Pure: step ids in, next state out. No network, no storage.
export const onboardingSteps = ['welcome', 'interview', 'documents', 'review', 'ready'] as const;
export type OnboardingStep = (typeof onboardingSteps)[number];

export type OnboardingState = { index: number };

export const initialOnboarding: OnboardingState = { index: 0 };

const last = onboardingSteps.length - 1;

export const stepOf = (s: OnboardingState): OnboardingStep => onboardingSteps[Math.min(Math.max(s.index, 0), last)]!;
export const canGoBack = (s: OnboardingState): boolean => s.index > 0;
export const isLast = (s: OnboardingState): boolean => s.index >= last;
export const next = (s: OnboardingState): OnboardingState => ({ index: Math.min(s.index + 1, last) });
export const back = (s: OnboardingState): OnboardingState => ({ index: Math.max(s.index - 1, 0) });
