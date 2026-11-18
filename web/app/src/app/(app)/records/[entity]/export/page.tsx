import { notFound } from 'next/navigation';
import { ExportDialog } from '../../../../../components/records/ExportDialog';
import { fixtureCaller, fixtureData } from '../../../../../records/fixture/rows';
import styles from '../../../../../components/records/Records.module.css';

// Static export (ADR-0022): one page per Blueprint entity from the fixture. Exports are built in the browser from the fixture.
export const dynamicParams = false;
export const generateStaticParams = () => fixtureData.entities.map((e) => ({ entity: e.id }));

export default async function ExportPage({ params }: { params: Promise<{ entity: string }> }) {
  const { entity } = await params;
  if (!fixtureData.entities.some((e) => e.id === entity)) notFound();
  return (
    <div className={styles.page}>
      <ExportDialog data={fixtureData} entityId={entity} caller={fixtureCaller} />
    </div>
  );
}
