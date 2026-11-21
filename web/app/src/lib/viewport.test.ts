import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { DRAWER_MAX_PX, usesDrawer, viewportClass } from './viewport';

describe('viewport classes', () => {
  it('classifies the target widths', () => {
    expect(viewportClass(375)).toBe('phone');
    expect(viewportClass(599)).toBe('phone');
    expect(viewportClass(600)).toBe('tablet');
    expect(viewportClass(768)).toBe('tablet');
    expect(viewportClass(1024)).toBe('desktop');
  });
  it('uses the drawer at 375 and 768 but not on desktop', () => {
    expect(usesDrawer(375)).toBe(true);
    expect(usesDrawer(768)).toBe(true);
    expect(usesDrawer(769)).toBe(false);
  });
  it('matches the shell CSS breakpoint (48rem)', () => {
    const css = readFileSync(join(__dirname, '../components/shell/Shell.module.css'), 'utf8');
    expect(css).toContain(`@media (max-width: ${DRAWER_MAX_PX / 16}rem)`);
  });
});
