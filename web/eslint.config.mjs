import js from '@eslint/js';
import tseslint from 'typescript-eslint';

// The authoritative token/logical-property gate is scripts/check-tokens-only.mjs (also covers CSS).
// These selectors catch the same colour and font literals inside TS/TSX string literals.
const noLiterals = [
  { selector: "Literal[value=/#[0-9a-fA-F]{3,8}\\b/]", message: 'No hex colour literals; use var(--color-*).' },
  { selector: "Literal[value=/\\b(rgba?|hsla?|oklch|oklab)\\(/i]", message: 'No colour function literals; use var(--color-*).' },
  { selector: "Property[key.name='fontFamily'] > Literal:not([value=/var\\(/])", message: 'No font-family literals; use var(--font-*).' },
];

export default tseslint.config(
  { ignores: ['**/node_modules/**', '**/.next/**', '**/out/**', 'app/theme/**', '**/next-env.d.ts'] },
  js.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    extends: [...tseslint.configs.recommended],
    rules: { 'no-restricted-syntax': ['error', ...noLiterals] },
  },
  {
    files: ['**/*.mjs'],
    languageOptions: { globals: { process: 'readonly', console: 'readonly' } },
  },
);
