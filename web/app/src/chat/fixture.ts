import { createFakePort, type FakePort } from './fake';
import type { ChatEvent, SendRequest } from './types';

// Synthetic script for the preview route until the stream client (WEB-026) exists. It reacts to the
// mode and a few words only; it is not a model and holds no data.
let n = 0;
const id = (p: string) => `${p}-${++n}`;

export function fixtureScript(req: SendRequest): ReadonlyArray<ChatEvent> {
  const text = req.text.trim().toLowerCase();
  if (text.length < 3) return [{ type: 'abstain', clarifyKey: 'whichRecord' }, { type: 'run_finished', outcome: 'done' }];
  const m = id('m');
  const say = (t: string): ChatEvent[] => [
    { type: 'text_delta', messageId: m, delta: t.slice(0, Math.ceil(t.length / 2)) },
    { type: 'text_delta', messageId: m, delta: t.slice(Math.ceil(t.length / 2)) },
    { type: 'text_end', messageId: m },
  ];
  const call = id('c');
  if (text.includes('approval') || text.includes('اعتماد')) {
    return [
      { type: 'tool_call', callId: call, tool: 'sales_order.submit', risk: 'R3' },
      { type: 'tool_result', callId: call, outcome: 'pending_approval' },
      { type: 'approval_pending', approvalId: id('a'), tool: 'sales_order.submit', risk: 'R3' },
      { type: 'run_finished', outcome: 'interrupt' },
    ];
  }
  if (req.mode === 'act' || req.mode === 'change') {
    return [
      { type: 'tool_call', callId: call, tool: 'sales_order.update', risk: 'R2' },
      { type: 'tool_result', callId: call, outcome: 'ok' },
      { type: 'confirm_required', confirmId: id('k'), tool: 'sales_order.update', risk: 'R2', changes: [{ label: 'Status', before: 'Draft', after: 'Confirmed' }] },
      { type: 'run_finished', outcome: 'interrupt' },
    ];
  }
  return [
    { type: 'tool_call', callId: call, tool: 'sales_order.list', risk: 'R0' },
    { type: 'tool_result', callId: call, outcome: 'ok' },
    ...say('You have 3 open orders. لديك ثلاثة أوامر بيع مفتوحة.'),
    { type: 'run_finished', outcome: 'done' },
  ];
}

export const createFixturePort = (): FakePort => createFakePort(fixtureScript, { delayMs: 350 });
