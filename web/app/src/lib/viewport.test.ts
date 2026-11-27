import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { DRAWER_MAX_PX, RAIL_MAX_PX, usesDrawer, usesRail, viewportClass } from './viewport';

describe('viewport classes', () => {
  it('classifies the target widths', () => {
    expect(viewportClass(375)).toBe('phone');
    expect(viewportClass(599)).toBe('phone');
    expect(viewportClass(600)).toBe('tablet');
    expect(viewportClass(768)).toBe('tablet');
    expect(viewportClass(1024)).toBe('desktop');
  });
  it('uses the drawer on phones only; tablets (768 to 1023) get the icon rail (WEB-029)', () => {
    expect(usesDrawer(375)).toBe(true);
    expect(usesDrawer(767)).toBe(true);
    expect(usesDrawer(768)).toBe(false);
    expect(usesRail(767)).toBe(false);
    expect(usesRail(768)).toBe(true);
    expect(usesRail(1023)).toBe(true);
    expect(usesRail(1024)).toBe(false);
  });
  it('matches the shell CSS breakpoints (drawer below 48rem, rail from 48rem to below 64rem)', () => {
    const css = readFileSync(join(__dirname, '../components/shell/Shell.module.css'), 'utf8');
    expect(css).toContain(`@media (max-width: ${DRAWER_MAX_PX / 16}rem)`);
    expect(css).toContain(`@media (min-width: ${(DRAWER_MAX_PX + 1) / 16}rem) and (max-width: ${RAIL_MAX_PX / 16}rem)`);
  });
});
