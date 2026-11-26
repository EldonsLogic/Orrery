// WEB-007: the preview's committed colour data must equal what the generator makes from the canonical tokens.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { SOURCE, TARGET, renderBrandingColours } from './gen-branding-colours.mjs';

test('colour.tokens.generated.json matches docs/brand/tokens/tokens.json (run: node scripts/gen-branding-colours.mjs)', () => {
  const want = renderBrandingColours(JSON.parse(readFileSync(SOURCE, 'utf8')));
  assert.equal(readFileSync(TARGET, 'utf8'), want);
});

test('drift is detected', () => {
  const tokens = JSON.parse(readFileSync(SOURCE, 'utf8'));
  tokens.color.light.background.hex = '#010203';
  assert.notEqual(readFileSync(TARGET, 'utf8'), renderBrandingColours(tokens));
});
