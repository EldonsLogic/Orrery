// WEB-029: chat screen design pass. Presentation contracts on top of the WEB-004 behaviour tests (chat.test.tsx).
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import type { ReactElement } from 'react';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { NextIntlClientProvider } from 'next-intl';
import { messages } from '../i18n';
import { ChatScreen } from '../components/chat/ChatScreen';
import { ApprovalCard, ChatError, ClarifyPrompt, ConfirmCard } from '../components/chat/Cards';
import { Composer } from '../components/chat/Composer';
import { MessageList, Thinking } from '../components/chat/Messages';
import { createFakePort } from './fake';
import { fixtureScript } from './fixture';
import { parseChatEvent, parseSources, sourceHref } from './events';
import { chatReducer, initialChatState } from './reducer';
import type { ChatEvent, ChatMessage } from './types';

const render = (locale: 'en' | 'ar', node: ReactElement) =>
  renderToString(
    <div dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone="UTC">
        {node}
      </NextIntlClientProvider>
    </div>,
  );
const sheet = readFileSync(join(__dirname, '../components/chat/Chat.module.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
const answer: ChatMessage = {
  id: 'm1',
  role: 'assistant',
  text: 'You have 3 open sales orders worth SAR 71,875.00.',
  streaming: false,
  sources: [
    { entity: 'sales_order', id: 'SO-00001' },
    { entity: 'sales_order', id: 'SO-00002' },
  ],
};

describe('source records', () => {
  it('accepts well-formed sources only, deduplicated and capped', () => {
    expect(parseSources([{ entity: 'sales_order', id: 'SO-00001' }, { entity: 'sales_order', id: 'SO-00001' }])).toEqual([{ entity: 'sales_order', id: 'SO-00001' }]);
    expect(parseSources([{ entity: '../admin', id: 'x' }])).toBeNull();
    expect(parseSources([{ entity: 'sales_order', id: 'a/b' }])).toBeNull();
    expect(parseSources([{ entity: 'sales_order', id: 'javascript:alert(1)' }])).toBeNull();
    expect(parseSources(Array.from({ length: 11 }, (_, i) => ({ entity: 'item', id: `ITM-${i}` })))).toBeNull();
    expect(parseChatEvent({ type: 'sources', messageId: 'm1', records: [{ entity: 'item', id: 'ITM-001', url: 'https://e.test' }] })).toEqual({
      type: 'sources',
      messageId: 'm1',
      records: [{ entity: 'item', id: 'ITM-001' }],
    });
    expect(parseChatEvent({ type: 'sources', messageId: 'm1', records: 'SO-1' })).toBeNull();
    expect(sourceHref({ entity: 'sales_order', id: 'SO-00001' })).toBe('/records/sales_order/SO-00001/');
  });
  it('attaches sources to the matching Seshna message only', () => {
    let s = chatReducer(initialChatState(), { kind: 'user_send', id: 'u1', text: 'open orders' });
    const ev = (event: ChatEvent) => (s = chatReducer(s, { kind: 'event', event }));
    ev({ type: 'text_delta', messageId: 'm1', delta: 'Three.' });
    ev({ type: 'sources', messageId: 'm1', records: [{ entity: 'sales_order', id: 'SO-00001' }] });
    ev({ type: 'sources', messageId: 'u1', records: [{ entity: 'sales_order', id: 'SO-00002' }] });
    expect(s.messages.find((m) => m.id === 'm1')?.sources).toHaveLength(1);
    expect(s.messages.find((m) => m.id === 'u1')?.sources).toBeUndefined();
  });
  it('the fixture answer cites its records and answers in the language asked', () => {
    const en = fixtureScript({ text: 'show open orders', mode: 'ask' });
    expect(en.find((e) => e.type === 'sources')).toBeTruthy();
    const ar = fixtureScript({ text: 'ما أوامر البيع المفتوحة؟', mode: 'ask' });
    const text = ar.filter((e) => e.type === 'text_delta').map((e) => (e as { delta: string }).delta).join('');
    expect(text).toMatch(/أوامر/);
  });
});

describe('turns', () => {
  for (const l of ['en', 'ar'] as const) {
    it(`Seshna turns carry the mark and cite records as links; user turns are a pill at the end side (${l})`, () => {
      const out = render(l, <MessageList messages={[{ id: 'u1', role: 'user', text: 'open orders?', streaming: false }, answer]} />);
      expect(out).toMatch(/data-role="assistant"[\s\S]*<svg/);
      expect(out).toMatch(/<li[^>]*data-role="user"[^>]*>(?:(?!<\/li>).)*class="[^"]*userPill/);
      expect(out).not.toMatch(/data-role="user"(?:(?!<\/li>).)*<svg/);
      expect(out).toMatch(/href="\/records\/sales_order\/SO-00001\/?"/);
      expect(out).toMatch(/href="\/records\/sales_order\/SO-00002\/?"/);
      expect(out).toContain(messages[l].chat.sources.label);
      expect(out).toContain('<bdi>Seshna</bdi>');
    });
  }
  it('sets figures in tabular numbers and never mirrors them', () => {
    expect(sheet).toMatch(/\.text \{[^}]*font-variant-numeric: tabular-nums/);
    expect(sheet).toMatch(/\.sourceChip \{[^}]*font-variant-numeric: tabular-nums/);
    expect(sheet).not.toMatch(/scaleX|rotateY/);
  });
  it('shows Seshna thinking with the loading mark and a visible label', () => {
    const out = render('en', <Thinking label={messages.en.chat.stream.working} />);
    expect(out).toContain('role="status"');
    expect(out).toContain('Seshna is working');
  });
  it('blinks the streaming caret only when motion is allowed', () => {
    const caret = sheet.slice(sheet.indexOf('@media (prefers-reduced-motion: no-preference)'));
    expect(caret).toMatch(/animation:/);
    expect(sheet.slice(0, sheet.indexOf('@media (prefers-reduced-motion: no-preference)'))).not.toMatch(/animation:/);
  });
});

describe('proposal cards', () => {
  const confirm = { confirmId: 'k1', tool: 'sales_order.update', risk: 'R2' as const, changes: [{ label: 'Status', before: 'Draft', after: 'Confirmed' }] };
  for (const l of ['en', 'ar'] as const) {
    const m = messages[l].chat;
    it(`a confirmation is a drafted proposal with confirm, edit and cancel (${l})`, () => {
      const out = render(l, <ConfirmCard confirm={confirm} onAnswer={() => {}} onEdit={() => {}} />);
      expect(out).toContain('data-status="drafted"');
      expect(out).toContain(messages[l].marks.status.drafted);
      expect(out).toContain(`>${m.confirm.confirm}<`);
      expect(out).toContain(`>${m.confirm.edit}<`);
      expect(out).toContain(`>${m.confirm.cancel}<`);
      expect(out).toContain(m.confirm.note);
      expect(out).toContain(m.confirm.before);
      expect(out).toContain(m.confirm.after);
    });
    it(`a pending approval is a drafted proposal that links to the inbox and cannot be approved here (${l})`, () => {
      const out = render(l, <ApprovalCard approval={{ approvalId: 'a1', tool: 'sales_order.submit', risk: 'R3' }} />);
      expect(out).toContain('data-status="drafted"');
      expect(out).toMatch(/href="\/approvals\/?"/);
      expect(out).not.toContain('<button');
    });
  }
  it('says errors and refusals in plain words, and a clarification comes from Seshna', () => {
    expect(render('en', <ChatError code="forbidden" />)).toContain(messages.en.chat.errors.forbidden);
    const clarify = render('ar', <ClarifyPrompt clarifyKey="whichPeriod" />);
    expect(clarify).toContain(messages.ar.chat.clarify.whichPeriod);
    expect(clarify).toContain('<svg');
  });
});

describe('composer and empty state', () => {
  it('docks the composer in glass with the send button inside', () => {
    const out = render('en', <Composer mode="ask" running={false} onMode={() => {}} onSend={() => true} onCancel={() => {}} />);
    expect(out).toMatch(/class="[^"]*field[^"]*"[\s\S]*<textarea[\s\S]*<button[^>]*type="submit"/);
    expect(sheet).toMatch(/\.dock \{[^}]*position: sticky/);
    expect(sheet).toMatch(/\.field \{[^}]*backdrop-filter: var\(--glass-filter\)/);
    expect(sheet).not.toMatch(/backdrop-filter: (?!var)/);
  });
  for (const l of ['en', 'ar'] as const) {
    it(`greets with suggested prompts as buttons (${l})`, () => {
      const out = render(l, <ChatScreen port={createFakePort(fixtureScript)} roles={['owner']} />);
      expect(out).toContain(messages[l].chat.empty.title);
      expect(out).toMatch(/<button[^>]*>(?:(?!<\/button>).)*How much cash|<button[^>]*>(?:(?!<\/button>).)*النقد/);
      expect(out).not.toMatch(/>\s*Approve\s*</i);
    });
  }
  it('keeps every size on the foundation roles (no px in the stylesheet)', () => {
    expect(sheet).not.toMatch(/\d+px/);
  });
});
