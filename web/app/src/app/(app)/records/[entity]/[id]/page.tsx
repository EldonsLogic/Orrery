import { notFound } from 'next/navigation';
import { RecordFormScreen } from '../../../../../components/shell/RecordScreens';
import { fixtureData } from '../../../../../records/fixture/rows';
import styles from '../../../../../components/records/Records.module.css';

// `new` is the create form; every other segment is a fixture record id.
export const dynamicParams = false;
export const generateStaticParams = () =>
  fixtureData.entities.filter((e) => e.kind !== 'child').flatMap((e) => ['new', ...(fixtureData.rows[e.id] ?? []).map((r) => r.id)].map((id) => ({ entity: e.id, id })));

export default async function RecordFormPage({ params }: { params: Promise<{ entity: string; id: string }> }) {
  const { entity, id } = await params;
  if (!fixtureData.entities.some((e) => e.id === entity && e.kind !== 'child')) notFound();
  return (
    <div className={styles.page}>
      <RecordFormScreen entityId={entity} recordId={id === 'new' ? undefined : id} />
    </div>
  );
}
