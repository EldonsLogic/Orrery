import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import { Providers } from './components/Providers';
import { Preview } from './components/Preview';
import { formatNumber } from './lib/format';
import ar from '../messages/ar.json';

describe('preview page', () => {
  const html = renderToString(
    <Providers>
      <Preview />
    </Providers>,
  );

  it('renders Arabic strings by default, colours only via var()', () => {
    expect(html).toContain(ar.preview.title);
    expect(html).toContain('var(--color-primary)');
    expect(html).not.toMatch(/#[0-9a-fA-F]{6}/);
  });

  it('shows Eastern Arabic digits when asked, explicitly', () => {
    expect(formatNumber('ar', 1234, 'arab')).toMatch(/[٠-٩]/);
    expect(formatNumber('en', 1234, 'latn')).toBe('1,234');
    expect(html).toMatch(/[٠-٩]/);
  });

  it('shows every component through i18n, tone roles included', () => {
    expect(html).toContain(ar.preview.components.title);
    expect(html).toContain(ar.preview.components.buttons.primary);
    expect(html).toContain(ar.preview.components.table.caption);
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain('role="alert"');
    expect(html).toContain('role="status"');
    expect(html).toContain('scope="row"');
  });
});
