import test from 'node:test';
import assert from 'node:assert/strict';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { scanDirs, scanText } from './check-rtl-css.mjs';

const rules = (t) => scanText(t).map((x) => x.rule);

test('logical CSS passes', () => {
  assert.deepEqual(rules('.a { margin-inline-start: 4px; padding-inline: 2px; inset-inline-end: 0; text-align: start; border-start-start-radius: 2px; }'), []);
});
test('rejects physical box, offset, align, float and radius', () => {
  assert.deepEqual(rules('.a { margin-left: 4px; }'), ['physical-box']);
  assert.deepEqual(rules('.a { padding-right: 4px; }'), ['physical-box']);
  assert.deepEqual(rules('.a { border-left-width: 1px; }'), ['physical-box']);
  assert.deepEqual(rules('.a { left: 0; }'), ['physical-offset']);
  assert.deepEqual(rules('.a { text-align: right; }'), ['physical-align']);
  assert.deepEqual(rules('.a { float: left; }'), ['physical-align']);
  assert.deepEqual(rules('.a { border-top-right-radius: 4px; }'), ['physical-radius']);
  assert.deepEqual(rules('.a { background-position: left center; }'), ['physical-origin']);
});
test('rejects translateX and scaleX without a counterpart', () => {
  assert.deepEqual(rules('.a { transform: translateX(10px); }'), ['translate-x']);
  assert.deepEqual(rules('.a { transform: scaleX(-1); }'), ['rotate-scale-x']);
});
test('a [dir=rtl] counterpart on the line is accepted', () => {
  assert.deepEqual(rules('[dir="rtl"] .a { transform: scaleX(-1); }'), []);
});
test('rtl-ok comment needs a reason and works on the line or the line above', () => {
  assert.deepEqual(rules('.a { left: 0; } /* rtl-ok: spinner is symmetric */'), []);
  assert.deepEqual(rules('/* rtl-ok: always LTR code block */\n.a { left: 0; }'), []);
  assert.deepEqual(rules('.a { left: 0; } /* rtl-ok: */'), ['physical-offset']);
});
test('reports file and line', () => {
  assert.deepEqual(scanText('.a{}\n.b { right: 1px; }', 'x.css').map((f) => [f.file, f.line]), [['x.css', 2]]);
});
test('current web sources have no RTL violations', () => {
  const root = join(dirname(fileURLToPath(import.meta.url)), '..');
  assert.deepEqual(scanDirs([join(root, 'app/src'), join(root, 'marketing/src')]), []);
});
