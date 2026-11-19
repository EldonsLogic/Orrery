// Synthetic data for the viewer until the gateway serves the tenant's Blueprint (PLT-009) and its diff
// (BPL-006). The Blueprint is a trimmed copy of contracts/examples; the pending changes are invented.
import blueprint from './blueprint.json';
import type { Blueprint, DiffOp } from '../types';

export const fixtureBlueprint = blueprint as unknown as Blueprint;

export const fixturePending: ReadonlyArray<DiffOp> = [
  { op: 'replace', impact: 'compliance', schemaPath: '/workflows/*/transitions/*/guards/*/value', subject: { kind: 'transition', id: 'submit_large' }, labels: { before: { en: 'Send for approval', ar: 'إرسال للاعتماد' }, after: { en: 'Send for approval', ar: 'إرسال للاعتماد' } } },
  { op: 'add', impact: 'access', schemaPath: '/roles/*/permissions/*', subject: { kind: 'permission', id: 'item' }, labels: { before: null, after: { en: 'Warehouse keeper', ar: 'أمين مستودع' } } },
  { op: 'add', impact: 'config', schemaPath: '/entities/*/fields/*', subject: { kind: 'field', id: 'delivery_note' }, labels: { before: null, after: { en: 'Delivery note', ar: 'ملاحظة التسليم' } } },
  { op: 'replace', impact: 'branding', schemaPath: '/branding/primaryColour', subject: { kind: 'branding', id: 'branding' }, labels: null },
];
