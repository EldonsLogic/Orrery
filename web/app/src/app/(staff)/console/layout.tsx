import type { ReactNode } from 'react';
import { ConsoleProvider } from '../../../components/console/ConsoleProvider';
import { ConsoleShell } from '../../../components/console/ConsoleShell';

// Staff-only back office (PLT-012). Own route group, own session: it never shares the customer
// SessionProvider. Static export (ADR-0022): the real staff-realm check lives in the gateway and
// identity, never in this file; this layout only renders what the session view-model allows.
export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return (
    <ConsoleProvider>
      <ConsoleShell>{children}</ConsoleShell>
    </ConsoleProvider>
  );
}
