'use client';

import { useCallback, useEffect, useReducer, useRef } from 'react';
import { plainText } from './text';
import { MAX_MESSAGE_LENGTH } from './types';
import { chatReducer, initialChatState } from './reducer';
import type { ChatMode, ChatPort } from './types';

/** Binds a ChatPort to the reducer. Sending, cancelling and confirming go out through the port. */
export function useChat(port: ChatPort) {
  const [state, dispatch] = useReducer(chatReducer, undefined, () => initialChatState());
  const counter = useRef(0);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => port.subscribe((event) => dispatch({ kind: 'event', event })), [port]);

  const send = useCallback(
    (text: string) => {
      const s = stateRef.current;
      const clean = plainText(text).slice(0, MAX_MESSAGE_LENGTH);
      if (s.run !== 'idle' || !clean.trim()) return false;
      counter.current += 1;
      dispatch({ kind: 'user_send', id: `u-${counter.current}`, text: clean });
      port.send({ text: clean, mode: s.mode });
      return true;
    },
    [port],
  );
  const cancel = useCallback(() => {
    dispatch({ kind: 'cancel' });
    port.cancel();
  }, [port]);
  const respond = useCallback(
    (confirmId: string, accepted: boolean) => {
      dispatch({ kind: 'confirm_answered' });
      port.respond({ confirmId, accepted });
    },
    [port],
  );
  const setMode = useCallback((mode: ChatMode) => dispatch({ kind: 'mode', mode }), []);
  return { state, send, cancel, respond, setMode };
}
