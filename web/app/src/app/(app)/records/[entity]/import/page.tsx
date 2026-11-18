import { notFound } from 'next/navigation';
import { ImportWizard } from '../../../../../components/records/ImportWizard';
import { fixtureCaller, fixtureData } from '../../../../../records/fixture/rows';
import styles from '../../../../../components/records/Records.module.css';

// Static export (ADR-0022): one page per Blueprint entity from the fixture. Writes wait for the gateway (PLT-009).
export const dynamicParams = false;
export const generateStaticParams = () => fixtureData.entities.map((e) => ({ entity: e.id }));

export default async function ImportPage({ params }: { params: Promise<{ entity: string }> }) {
  const { entity } = await params;
  if (!fixtureData.entities.some((e) => e.id === entity)) notFound();
  return (
    <div className={styles.page}>
      <ImportWizard data={fixtureData} entityId={entity} caller={fixtureCaller} />
    </div>
  );
}
