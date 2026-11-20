// Viewport classes (WEB-013). Pure. The CSS media queries are the source of truth for layout;
// this mirrors their breakpoint so script (drawer close) and tests agree with the CSS.
export const DRAWER_MAX_PX = 768; // 48rem at the default 16px root: the shell's drawer breakpoint
export const PHONE_MAX_PX = 599;
export const TABLET_MAX_PX = 1023;

export type ViewportClass = 'phone' | 'tablet' | 'desktop';

export function viewportClass(widthPx: number): ViewportClass {
  if (widthPx <= PHONE_MAX_PX) return 'phone';
  if (widthPx <= TABLET_MAX_PX) return 'tablet';
  return 'desktop';
}

/** True when the side navigation is a drawer (matches `@media (max-width: 48rem)` in Shell.module.css). */
export const usesDrawer = (widthPx: number): boolean => widthPx <= DRAWER_MAX_PX;
