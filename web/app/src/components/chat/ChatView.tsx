'use client';

import { useMemo } from 'react';
import { createFixturePort } from '../../chat/fixture';
import { useSession } from '../shell/SessionProvider';
import { ChatScreen } from './ChatScreen';

/** The /chat route body. Fixture port until the AG-UI client (WEB-026) is wired. */
export function ChatView() {
  const { session } = useSession();
  const port = useMemo(() => createFixturePort(), []);
  if (session.status !== 'ready') return null;
  return <ChatScreen port={port} roles={session.claims.roles} />;
}
