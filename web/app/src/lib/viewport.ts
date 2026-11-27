// Viewport classes (WEB-013). Pure. The CSS media queries are the source of truth for layout;
// this mirrors their breakpoint so script (drawer close) and tests agree with the CSS.
export const DRAWER_MAX_PX = 767; // below 48rem (768) at the default 16px root: the shell's drawer breakpoint
/** The icon-rail side navigation spans the tablet range, 48rem (768) up to below 64rem (1024). */
export const RAIL_MAX_PX = 1023;
export const PHONE_MAX_PX = 599;
export const TABLET_MAX_PX = 1023;

export type ViewportClass = 'phone' | 'tablet' | 'desktop';

export function viewportClass(widthPx: number): ViewportClass {
  if (widthPx <= PHONE_MAX_PX) return 'phone';
  if (widthPx <= TABLET_MAX_PX) return 'tablet';
  return 'desktop';
}

/** True when the side navigation is a drawer (matches `@media (max-width: 47.9375rem)` in Shell.module.css). */
export const usesDrawer = (widthPx: number): boolean => widthPx <= DRAWER_MAX_PX;

/** True when the side navigation is a collapsed icon rail (tablet). */
export const usesRail = (widthPx: number): boolean => widthPx > DRAWER_MAX_PX && widthPx <= RAIL_MAX_PX;
