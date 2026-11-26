// WEB-004: pure chat layer (reducer, fake port, allow-list) and server-rendered screen in en and ar.
import { describe, expect, it } from 'vitest';
import { renderToString } from 'react-dom/server';
import type { ReactElement } from 'react';
import { NextIntlClientProvider } from 'next-intl';
import { messages } from '../i18n';
import { ChatScreen } from '../components/chat/ChatScreen';
import { ApprovalCard, ChatError, ClarifyPrompt, ConfirmCard } from '../components/chat/Cards';
import { Composer } from '../components/chat/Composer';
import { ActivityList, MessageList } from '../components/chat/Messages';
import { createFakePort } from './fake';
import { fixtureScript } from './fixture';
import { parseChatEvent } from './events';
import { chatReducer, initialChatState } from './reducer';
import { suggestionKeys } from './suggestions';
import { composerKeyAction, plainText, textLang } from './text';
import type { ChatEvent, ChatState } from './types';

const render = (locale: 'en' | 'ar', node: ReactElement) =>
  renderToString(
    <div dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      <NextIntlClientProvider locale={locale} messages={messages[locale]} timeZone="UTC">
        {node}
      </NextIntlClientProvider>
    </div>,
  );
const fold = (events: ChatEvent[], s: ChatState = { ...initialChatState('act'), run: 'running' }) =>
  events.reduce((acc, event) => chatReducer(acc, { kind: 'event', event }), s);
const port = () => createFakePort(fixtureScript);

describe('screen in both languages', () => {
  for (const l of ['en', 'ar'] as const) {
    const m = messages[l].chat;
    it(`renders the empty state, modes and role suggestions (${l})`, () => {
      const out = render(l, <ChatScreen port={port()} roles={['owner']} />);
      expect(out).toContain(m.title);
      expect(out).toContain(m.suggestions.owner.cash);
      for (const mode of ['discover', 'ask', 'act', 'change'] as const) expect(out).toContain(m.mode[mode].name);
      expect(out).toContain(m.mode.hint);
      expect(out).toContain(m.mode.ask.description); // active mode explained
      expect(out.startsWith(`<div dir="${l === 'ar' ? 'rtl' : 'ltr'}"`)).toBe(true);
      expect(out).not.toMatch(/style="[^"]*(?:left|right)\s*:/);
    });
  }
  it('uses the generic suggestions for an unknown role', () => {
    expect(suggestionKeys(['nobody'])[0]).toBe('generic.what');
    expect(suggestionKeys(['accountant', 'owner'])[0]).toBe('accountant.overdue');
  });
  it('keeps the composer focusable but read-only and offers stop while a run is active', () => {
    const idle = render('en', <Composer mode="ask" running={false} onMode={() => {}} onSend={() => true} onCancel={() => {}} />);
    const busy = render('en', <Composer mode="ask" running onMode={() => {}} onSend={() => true} onCancel={() => {}} />);
    expect(idle).not.toMatch(/<textarea[^>]*(?:disabled|readOnly|aria-disabled)/);
    expect(busy).not.toMatch(/<textarea[^>]*\sdisabled/);
    expect(busy).toMatch(/<textarea[^>]*readOnly/);
    expect(busy).toMatch(/<textarea[^>]*aria-disabled="true"/);
    expect(busy).toContain('>Stop<');
    expect(busy).not.toContain('>Send<');
    expect(idle).toContain('maxLength="4000"');
  });
});

describe('language of text (A-11)', () => {
  it('detects by script and leaves mixed text to inherit', () => {
    expect(textLang('مرحبا')).toBe('ar');
    expect(textLang('hello 123')).toBe('en');
    expect(textLang('فاتورة INV-001')).toBeUndefined();
    expect(textLang('123')).toBeUndefined();
  });
  it('sets lang on single-language bubbles', () => {
    const out = render('en', <MessageList messages={[{ id: 'a', role: 'assistant', text: 'مرحبا', streaming: false }]} />);
    expect(out).toContain('<bdi lang="ar">');
  });
});

describe('text safety', () => {
  it('renders model text as escaped plain text in an isolated bubble', () => {
    const out = render('en', <MessageList messages={[{ id: 'a', role: 'assistant', text: '<img src=x onerror=alert(1)> <a href="https://e.test">x</a> **b**', streaming: false }]} />);
    expect(out).not.toContain('<img');
    expect(out).not.toContain('<a ');
    expect(out).toContain('&lt;img');
    expect(out).toContain('**b**');
    expect(out).toContain('dir="auto"');
    expect(out).toContain('<bdi lang="en">');
  });
  it('mixes Arabic and English in one message', () => {
    const out = render('ar', <MessageList messages={[{ id: 'a', role: 'assistant', text: 'Invoice INV-001 مستحقة', streaming: false }]} />);
    expect(out).toContain('Invoice INV-001 مستحقة');
  });
  it('strips bidi overrides and invisible characters', () => {
    expect(plainText('a‮b⁦c​d\u0000e')).toBe('abcde');
    expect(plainText('سطر\nثان')).toBe('سطر\nثان');
  });
});

describe('keyboard', () => {
  it('Enter sends, Shift+Enter and IME composition do not', () => {
    expect(composerKeyAction({ key: 'Enter', shiftKey: false })).toBe('send');
    expect(composerKeyAction({ key: 'Enter', shiftKey: true })).toBe('none');
    expect(composerKeyAction({ key: 'Enter', shiftKey: false, isComposing: true })).toBe('none');
    expect(composerKeyAction({ key: 'Enter', shiftKey: false, keyCode: 229 })).toBe('none');
    expect(composerKeyAction({ key: 'a', shiftKey: false })).toBe('none');
  });
});

describe('flows with the fake port', () => {
  it('send then stream: user message, partial text, done', () => {
    const p = createFakePort(fixtureScript, { manual: true });
    let s: ChatState = initialChatState('ask');
    p.subscribe((event) => (s = chatReducer(s, { kind: 'event', event })));
    s = chatReducer(s, { kind: 'user_send', id: 'u1', text: 'show orders' });
    p.send({ text: 'show orders', mode: 'ask' });
    expect(s.run).toBe('running');
    while (p.step() && !s.messages.some((m) => m.streaming)) {
      /* advance to the first partial text */
    }
    expect(s.messages.at(-1)?.streaming).toBe(true);
    while (p.step()) {
      /* finish */
    }
    expect(s.run).toBe('idle');
    expect(s.messages.at(-1)?.streaming).toBe(false);
    expect(s.activity[0]).toMatchObject({ risk: 'R0', outcome: 'ok' });
  });
  it('ignores a second send while running and cancel ends the run', () => {
    let s = chatReducer(initialChatState(), { kind: 'user_send', id: 'u1', text: 'hi there' });
    s = chatReducer(s, { kind: 'user_send', id: 'u2', text: 'again' });
    expect(s.messages).toHaveLength(1);
    s = chatReducer(s, { kind: 'cancel' });
    expect(s.run).toBe('cancelling');
    s = fold([{ type: 'run_finished', outcome: 'cancelled' }], s);
    expect(s.run).toBe('idle');
    const p = port();
    p.cancel();
    expect(p.cancelled).toBe(1);
  });
  it('act mode asks for confirmation and never confirms by itself', () => {
    const p = port();
    const seen: ChatEvent[] = [];
    p.subscribe((e) => seen.push(e));
    p.send({ text: 'confirm the order', mode: 'act' });
    const s = fold(seen);
    expect(s.confirm?.risk).toBe('R2');
    expect(p.decisions).toEqual([]);
    const out = render('en', <ConfirmCard confirm={s.confirm!} onAnswer={() => {}} />);
    expect(out).toContain('Order date: 2026-03-06 to 2026-03-09'); // WEB-029: fixture fields carry Blueprint ids
    expect(out).toContain('>Confirm<');
    expect(out).toContain('>Cancel<');
    p.respond({ confirmId: s.confirm!.confirmId, accepted: true });
    expect(p.decisions).toHaveLength(1);
  });
  it('approval-required shows sent for approval with a link and no approve button', () => {
    const p = port();
    const seen: ChatEvent[] = [];
    p.subscribe((e) => seen.push(e));
    p.send({ text: 'send for approval', mode: 'act' });
    const s = fold(seen);
    expect(s.approvals).toHaveLength(1);
    expect(s.activity[0].outcome).toBe('pending_approval');
    for (const l of ['en', 'ar'] as const) {
      const out = render(l, <ApprovalCard approval={s.approvals[0]} />);
      expect(out).toContain('href="/approvals"');
      expect(out).not.toContain('<button');
      expect(out).toContain(messages[l].chat.approval.title);
    }
    const full = render('en', <ChatScreen port={p} roles={[]} />);
    expect(full).not.toMatch(/>\s*Approve\s*</i);
  });
  it('abstain shows a clarify prompt and errors map to domain messages', () => {
    const s = fold([{ type: 'abstain', clarifyKey: 'whichPeriod' }]);
    expect(render('en', <ClarifyPrompt clarifyKey={s.clarifyKey!} />)).toContain(messages.en.chat.clarify.whichPeriod);
    // QA-014 review: it sits inside the persistent live region, so it must not be a second live region.
    expect(render('en', <ClarifyPrompt clarifyKey="generic" />)).not.toContain('role="status"');
    expect(render('ar', <ClarifyPrompt clarifyKey="made-up" />)).toContain(messages.ar.chat.clarify.generic);
    const e = fold([{ type: 'run_error', code: 'forbidden' }]);
    expect(e.run).toBe('idle');
    expect(render('ar', <ChatError code={e.errorCode!} />)).toContain(messages.ar.chat.errors.forbidden);
    expect(render('en', <ChatError code="SELECT * FROM x" />)).toContain(messages.en.chat.errors.unknown);
  });
  it('activity list shows tool, risk and outcome only', () => {
    const out = render('en', <ActivityList steps={[{ callId: 'c', tool: 'sales_order.list', risk: 'R1', outcome: 'denied' }]} />);
    expect(out).toContain('sales_order.list');
    expect(out).toContain('R1');
    expect(out).toContain('Not allowed');
  });
});

describe('event allow-list', () => {
  it('drops unknown types and malformed fields', () => {
    expect(parseChatEvent({ type: 'raw', data: 1 })).toBeNull();
    expect(parseChatEvent({ type: 'html', html: '<b>' })).toBeNull();
    expect(parseChatEvent({ type: 'tool_call', callId: 'c', tool: 't', risk: 'R9' })).toBeNull();
    expect(parseChatEvent(null)).toBeNull();
    expect(parseChatEvent({ type: 'tool_call', callId: 'c', tool: 't', risk: 'R2', args: { secret: 1 } })).toEqual({ type: 'tool_call', callId: 'c', tool: 't', risk: 'R2' });
    expect(parseChatEvent({ type: 'run_finished', outcome: 'done' })).not.toBeNull();
  });
});

describe('engine invisibility', () => {
  it('names no engine in messages or fixture', () => {
    const word = new RegExp(['fra', 'ppe|erp', 'next'].join(''), 'i');
    for (const l of ['en', 'ar'] as const) expect(JSON.stringify(messages[l].chat)).not.toMatch(word);
    expect(JSON.stringify(fixtureScript({ text: 'show orders', mode: 'act' }))).not.toMatch(word);
  });
});
