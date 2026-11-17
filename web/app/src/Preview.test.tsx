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
});
