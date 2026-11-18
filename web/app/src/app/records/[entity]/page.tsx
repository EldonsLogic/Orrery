import { notFound } from 'next/navigation';
import { RecordList } from '../../../components/records/RecordList';
import { fixtureCaller, fixtureData } from '../../../records/fixture/rows';
import styles from '../../../components/records/Records.module.css';

// Static export (ADR-0022): one page per Blueprint entity from the fixture. Data is synthetic until PLT-009.
export const dynamicParams = false;
export const generateStaticParams = () => fixtureData.entities.map((e) => ({ entity: e.id }));

export default async function RecordListPage({ params }: { params: Promise<{ entity: string }> }) {
  const { entity } = await params;
  if (!fixtureData.entities.some((e) => e.id === entity)) notFound();
  return (
    <main className={styles.page}>
      <RecordList data={fixtureData} entityId={entity} caller={fixtureCaller} />
    </main>
  );
}
