import test from 'node:test';
import assert from 'node:assert/strict';
import { scanText } from './check-tokens-only.mjs';

const rules = (t, f) => scanText(t, f).map((x) => x.rule);

test('clean token CSS passes', () => {
  assert.deepEqual(rules('.a { color: var(--color-text); margin-inline-start: 8px; text-align: start; font-family: var(--font-body); }'), []);
});
test('rejects hex and colour functions', () => {
  assert.deepEqual(rules('.a { color: #fff; }'), ['colour-hex']);
  assert.deepEqual(rules('.a { background: rgb(0 0 0); }'), ['colour-fn']);
  assert.deepEqual(rules('const c = "hsl(10 10% 10%)";'), ['colour-fn']);
});
test('rejects font-family literals but allows var()', () => {
  assert.deepEqual(rules('.a { font-family: Arial, sans-serif; }'), ['font-family']);
  assert.deepEqual(rules('const s = { fontFamily: "Arial" };'), ['font-family-js']);
  assert.deepEqual(rules('const s = { fontFamily: "var(--font-body)" };'), []);
});
test('rejects physical direction properties', () => {
  assert.deepEqual(rules('.a { margin-left: 4px; }'), ['physical-prop']);
  assert.deepEqual(rules('.a { padding-right: 4px; }'), ['physical-prop']);
  assert.deepEqual(rules('.a { left: 0; }'), ['physical-offset']);
  assert.deepEqual(rules('.a { text-align: right; }'), ['physical-align']);
  assert.deepEqual(rules('.a { border-top-left-radius: 4px; }'), ['physical-radius']);
  assert.deepEqual(rules('const s = { marginLeft: 4 };'), ['physical-js']);
});
test('token files are exempt', () => {
  assert.deepEqual(rules('a{color:#fff}', 'web/app/src/styles/tokens.generated.css'), []);
  assert.deepEqual(rules('a{color:#fff}', 'web/app/src/styles/tokens.proposed.generated.css'), []);
  assert.deepEqual(rules('a{color:#fff}', 'docs/brand/tokens/tokens.css'), []);
});
test('logical properties are not flagged', () => {
  assert.deepEqual(rules('.a { inset-inline-start: 0; border-inline-end: 1px solid var(--color-text); }'), []);
});
test('the @font-face file may name families, nothing else may', () => {
  assert.deepEqual(rules('@font-face { font-family: "Cairo"; }', 'app/src/styles/fonts.css'), []);
  assert.deepEqual(rules('@font-face { font-family: "Cairo"; }', 'app/src/styles/other.css'), ['font-family']);
  assert.deepEqual(rules('@font-face { color: #fff; }', 'app/src/styles/fonts.css'), ['colour-hex']);
  assert.deepEqual(rules('@font-face { font-family: "Cairo"; }', 'marketing/src/styles/fonts.css'), ['font-family']);
  assert.deepEqual(rules('@font-face { font-family: "Cairo"; }', 'app/src/components/styles/fonts.css'), ['font-family']);
  assert.deepEqual(rules('@font-face { font-family: "Cairo"; }', '/repo/web/app/src/styles/fonts.css'), []);
});
