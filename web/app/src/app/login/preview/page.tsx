import type { Metadata } from 'next';
import { LoginPreview } from '../../../components/login/LoginPreview';

export const metadata: Metadata = { robots: { index: false, follow: false } };

/** Dev-only preview of a fixture tenant look (?tenant=...). Off unless NEXT_PUBLIC_LOGIN_PREVIEW=1; never the production login. */
export default function LoginPreviewPage() {
  return <LoginPreview />;
}
