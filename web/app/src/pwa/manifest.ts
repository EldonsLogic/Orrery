// Web app manifest builder (WEB-013). Pure: strings and token CSS in, manifest object out.
// No colour literals here: the colours are read from the generated token CSS (ADR-0014).

export type ManifestText = { name: string; shortName: string; description: string };
export type ThemeColors = { light: string; dark: string };

export type WebManifest = {
  name: string;
  short_name: string;
  description: string;
  lang: string;
  dir: 'rtl' | 'ltr';
  id: string;
  start_url: string;
  scope: string;
  display: 'standalone';
  orientation: 'any';
  background_color: string;
  theme_color: string;
  icons: ReadonlyArray<{ src: string; sizes: string; type: string; purpose: 'any' }>;
};

/** Read the background colour for the light and dark themes from the generated token CSS. */
export function themeColorsFromTokens(css: string): ThemeColors {
  const root = /:root\s*\{([^}]*)\}/.exec(css)?.[1] ?? '';
  const dark = /:root\[data-theme="dark"\]\s*\{([^}]*)\}/.exec(css)?.[1] ?? '';
  const pick = (block: string): string | undefined => /--color-background:\s*(#[0-9a-fA-F]{3,8})\s*;/.exec(block)?.[1];
  const light = pick(root);
  const darkColor = pick(dark);
  if (!light || !darkColor) throw new Error('tokens: --color-background missing for light or dark theme');
  return { light, dark: darkColor };
}

export function buildManifest(text: ManifestText, colors: ThemeColors, locale: string, dir: 'rtl' | 'ltr'): WebManifest {
  return {
    name: text.name,
    short_name: text.shortName,
    description: text.description,
    lang: locale,
    dir,
    id: '/',
    start_url: '/home/',
    scope: '/',
    display: 'standalone',
    orientation: 'any',
    background_color: colors.light,
    theme_color: colors.light,
    // Brand app icon (docs/brand/logo/app-icon.svg), copied at build time. No PNG exports exist yet (Q-381).
    icons: [{ src: '/icons/app-icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' }],
  };
}
