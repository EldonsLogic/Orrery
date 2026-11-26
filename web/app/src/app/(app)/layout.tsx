import type { ReactNode } from 'react';
import { AppShell } from '../../components/shell/AppShell';
import { SessionProvider } from '../../components/shell/SessionProvider';
import { BrandLockup } from '../../components/shell/BrandLockup';

// The authenticated area (WEB-003). The route group adds no URL segment. Static export (ADR-0022):
// the session is client-side, so the real sign-in check also lives in the browser and the gateway,
// never in this file.
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <AppShell brand={<BrandLockup />}>{children}</AppShell>
    </SessionProvider>
  );
}
