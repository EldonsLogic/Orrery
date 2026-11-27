'use client';

import { useTranslations } from 'next-intl';
import { fakePort, fixtureReview } from '../../../approval/fixture';
import { Alert } from '../../../ui';
import { OwnerApprovalView } from '../../../components/approval/OwnerApprovalView';

const port = fakePort();

// WEB-027: fixture and a fake port only. Not wired to the live host until Q-544 and Q-505 are settled; no nav link.
export default function ApprovalPage() {
  const t = useTranslations('ownerApproval');
  return (
    <>
      <Alert tone="info" title={t('ui.sampleNotice')} />
      <OwnerApprovalView view={fixtureReview} port={port} />
    </>
  );
}
