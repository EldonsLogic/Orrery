import type { ChatEvent, ChatMode, ChatState } from './types';
import { MAX_MESSAGE_LENGTH } from './types';
import { plainText } from './text';

export const initialChatState = (mode: ChatMode = 'ask'): ChatState => ({
  mode,
  run: 'idle',
  messages: [],
  activity: [],
  confirm: null,
  approvals: [],
  clarifyKey: null,
  errorCode: null,
});

export type ChatAction =
  | { kind: 'mode'; mode: ChatMode }
  | { kind: 'user_send'; id: string; text: string }
  | { kind: 'cancel' }
  | { kind: 'confirm_answered' }
  | { kind: 'event'; event: ChatEvent };

export function chatReducer(s: ChatState, a: ChatAction): ChatState {
  switch (a.kind) {
    case 'mode':
      return s.run === 'idle' ? { ...s, mode: a.mode } : s;
    case 'user_send': {
      const text = plainText(a.text).slice(0, MAX_MESSAGE_LENGTH);
      if (s.run !== 'idle' || !text.trim()) return s;
      return {
        ...s,
        run: 'running',
        activity: [],
        confirm: null,
        clarifyKey: null,
        errorCode: null,
        messages: [...s.messages, { id: a.id, role: 'user', text, streaming: false }],
      };
    }
    case 'cancel':
      return s.run === 'running' ? { ...s, run: 'cancelling' } : s;
    case 'confirm_answered':
      return { ...s, confirm: null, run: s.run === 'idle' ? 'running' : s.run };
    case 'event':
      return onEvent(s, a.event);
  }
}

function onEvent(s: ChatState, e: ChatEvent): ChatState {
  switch (e.type) {
    case 'run_started':
      return { ...s, run: s.run === 'cancelling' ? 'cancelling' : 'running' };
    case 'text_delta': {
      const delta = plainText(e.delta);
      const has = s.messages.some((m) => m.id === e.messageId && m.role === 'assistant');
      return {
        ...s,
        messages: has
          ? s.messages.map((m) => (m.id === e.messageId ? { ...m, text: m.text + delta, streaming: true } : m))
          : [...s.messages, { id: e.messageId, role: 'assistant', text: delta, streaming: true }],
      };
    }
    case 'text_end':
      return { ...s, messages: s.messages.map((m) => (m.id === e.messageId ? { ...m, streaming: false } : m)) };
    case 'sources':
      return { ...s, messages: s.messages.map((m) => (m.id === e.messageId && m.role === 'assistant' ? { ...m, sources: e.records } : m)) };
    case 'tool_call':
      return { ...s, activity: [...s.activity, { callId: e.callId, tool: e.tool, risk: e.risk, outcome: 'running' }] };
    case 'tool_result':
      return { ...s, activity: s.activity.map((x) => (x.callId === e.callId ? { ...x, outcome: e.outcome } : x)) };
    case 'confirm_required':
      return { ...s, confirm: { confirmId: e.confirmId, tool: e.tool, risk: e.risk, changes: e.changes, ...(e.record ? { record: e.record } : {}) } };
    case 'approval_pending':
      return s.approvals.some((x) => x.approvalId === e.approvalId)
        ? s
        : { ...s, approvals: [...s.approvals, { approvalId: e.approvalId, tool: e.tool, risk: e.risk, ...(e.record ? { record: e.record } : {}) }] };
    case 'abstain':
      return { ...s, clarifyKey: e.clarifyKey };
    case 'run_error':
      return { ...s, errorCode: e.code, run: 'idle', confirm: null, messages: s.messages.map((m) => ({ ...m, streaming: false })) };
    case 'run_finished':
      // A run that ends on an interrupt keeps its confirm card; anything else closes the run.
      return { ...s, run: 'idle', messages: s.messages.map((m) => ({ ...m, streaming: false })), confirm: e.outcome === 'cancelled' ? null : s.confirm };
  }
}
