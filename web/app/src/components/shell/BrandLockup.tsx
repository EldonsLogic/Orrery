import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/** Builds the inline lockup from the generated logo file (never redrawn or retyped): the mark takes the Seshna mark token, the wordmark the text token. */
export function lockupMarkup(svg: string): string {
  return svg
    .replace(/<\?xml[^>]*>\s*/, '')
    .replace(/<title>[\s\S]*?<\/title>/, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/ width="[^"]*" height="[^"]*"/, ' aria-hidden="true" focusable="false"')
    .replace(/fill="#[0-9A-Fa-f]{6}"/, 'fill="currentColor" data-part="mark"')
    .replace(/fill="#[0-9A-Fa-f]{6}"/g, 'fill="currentColor" data-part="word"');
}

/** Server component: read at build time (static export), so no logo request and the colours follow the theme. */
export function BrandLockup({ className }: { className?: string }) {
  const svg = readFileSync(join(process.cwd(), '../../docs/brand/logo/lockup-primary.svg'), 'utf8');
  return (
    <span className={className} role="img" aria-label="Seshna" dangerouslySetInnerHTML={{ __html: lockupMarkup(svg) }} />
  );
}
