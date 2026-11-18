import { notFound } from 'next/navigation';
import { RecordForm } from '../../../../components/records/RecordForm';
import { fixtureCaller, fixtureData } from '../../../../records/fixture/rows';
import styles from '../../../../components/records/Records.module.css';

// `new` is the create form; every other segment is a fixture record id.
export const dynamicParams = false;
export const generateStaticParams = () =>
  fixtureData.entities.flatMap((e) => ['new', ...(fixtureData.rows[e.id] ?? []).map((r) => r.id)].map((id) => ({ entity: e.id, id })));

export default async function RecordFormPage({ params }: { params: Promise<{ entity: string; id: string }> }) {
  const { entity, id } = await params;
  if (!fixtureData.entities.some((e) => e.id === entity)) notFound();
  return (
    <main className={styles.page}>
      <RecordForm data={fixtureData} entityId={entity} caller={fixtureCaller} recordId={id === 'new' ? undefined : id} />
    </main>
  );
}
