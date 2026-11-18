import { notFound } from 'next/navigation';
import { RecordListScreen } from '../../../../components/shell/RecordScreens';
import { fixtureData } from '../../../../records/fixture/rows';
import styles from '../../../../components/records/Records.module.css';

// Static export (ADR-0022): one page per Blueprint entity from the fixture. Data is synthetic until PLT-009.
export const dynamicParams = false;
export const generateStaticParams = () => fixtureData.entities.map((e) => ({ entity: e.id }));

export default async function RecordListPage({ params }: { params: Promise<{ entity: string }> }) {
  const { entity } = await params;
  if (!fixtureData.entities.some((e) => e.id === entity)) notFound();
  return (
    <div className={styles.page}>
      <RecordListScreen entityId={entity} />
    </div>
  );
}
