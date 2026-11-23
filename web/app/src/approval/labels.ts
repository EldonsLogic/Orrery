// View-model label keys ("oa.state.awaiting", "quote.line.module") to message paths under `ownerApproval`.
// The catalogue is services/discovery/owner_approval/labels.json plus the quote catalogue, nested by dots.
export const messagePath = (key: string): string => {
  if (key === 'oa.summary.not_shown') return 'summary.not_shown_notice';
  return key.startsWith('oa.') ? key.slice(3) : key;
};

/** Minor-unit percent text from basis points: 1500 -> "15", 1450 -> "14.5" (display only, as the quote catalogue does). */
export const percentText = (bp: number): string => {
  const whole = Math.trunc(bp / 100);
  const frac = String(bp % 100).padStart(2, '0').replace(/0+$/, '');
  return frac ? `${whole}.${frac}` : String(whole);
};
