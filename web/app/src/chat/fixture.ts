import { createFakePort, type FakePort } from './fake';
import { textLang } from './text';
import type { ChatEvent, SendRequest } from './types';

// Synthetic script for the preview route until the stream client (WEB-026) exists. It reacts to the
// mode and a few words only; it is not a model and holds no data.
let n = 0;
const id = (p: string) => `${p}-${++n}`;

export function fixtureScript(req: SendRequest): ReadonlyArray<ChatEvent> {
  const text = req.text.trim().toLowerCase();
  if (text.length < 3) return [{ type: 'abstain', clarifyKey: 'whichRecord' }, { type: 'run_finished', outcome: 'done' }];
  const m = id('m');
  // Streams the text a few words at a time, as the real stream does.
  const say = (t: string): ChatEvent[] => {
    const words = t.split(/(?<= )/);
    const chunks: ChatEvent[] = [];
    for (let i = 0; i < words.length; i += 4) chunks.push({ type: 'text_delta', messageId: m, delta: words.slice(i, i + 4).join('') });
    return [...chunks, { type: 'text_end', messageId: m }];
  };
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
      {
        type: 'confirm_required',
        confirmId: id('k'),
        tool: 'sales_order.update',
        risk: 'R2',
        changes: [
          { label: 'Status', before: 'Draft', after: 'Confirmed' },
          { label: 'Delivery date', before: '2026-03-06', after: '2026-03-09' },
        ],
      },
      { type: 'run_finished', outcome: 'interrupt' },
    ];
  }
  return [
    { type: 'tool_call', callId: call, tool: 'sales_order.list', risk: 'R0' },
    { type: 'tool_result', callId: call, outcome: 'ok' },
    ...say(
      textLang(req.text) === 'ar'
        ? 'لديك 3 أوامر بيع مفتوحة قيمتها الإجمالية SAR 71,875.00، وأكبرها SO-00002 بقيمة SAR 70,380.00 وهو ينتظر الاعتماد'
        : 'You have 3 open sales orders worth SAR 71,875.00. The largest, SO-00002 at SAR 70,380.00, is waiting for approval.',
    ),
    {
      type: 'sources',
      messageId: m,
      records: [
        { entity: 'sales_order', id: 'SO-00001' },
        { entity: 'sales_order', id: 'SO-00002' },
        { entity: 'sales_order', id: 'SO-00006' },
      ],
    },
    { type: 'run_finished', outcome: 'done' },
  ];
}

export const createFixturePort = (): FakePort => createFakePort(fixtureScript, { delayMs: 350 });
