'use client';

import { RecordForm } from '../records/RecordForm';
import { RecordList } from '../records/RecordList';
import { fixtureData } from '../../records/fixture/rows';
import { callerOf } from '../../lib/session';
import { useSession } from './SessionProvider';

// The record screens take the caller as data; inside the shell it comes from the session claims.
export function RecordListScreen({ entityId }: { entityId: string }) {
  const { session } = useSession();
  if (session.status !== 'ready') return null;
  return <RecordList data={fixtureData} entityId={entityId} caller={callerOf(session.claims)} />;
}

export function RecordFormScreen({ entityId, recordId }: { entityId: string; recordId?: string }) {
  const { session } = useSession();
  if (session.status !== 'ready') return null;
  return <RecordForm data={fixtureData} entityId={entityId} caller={callerOf(session.claims)} recordId={recordId} />;
}
