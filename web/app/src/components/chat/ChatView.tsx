'use client';

import { useMemo } from 'react';
import { createFixturePort } from '../../chat/fixture';
import { useSession } from '../shell/SessionProvider';
import { ChatScreen } from './ChatScreen';

/** The /chat route body. Fixture port: the AG-UI client (`createAguiPort`, WEB-026) is built but needs the session's access token (Q-270). */
export function ChatView() {
  const { session } = useSession();
  const port = useMemo(() => createFixturePort(), []);
  if (session.status !== 'ready') return null;
  return <ChatScreen port={port} roles={session.claims.roles} />;
}
