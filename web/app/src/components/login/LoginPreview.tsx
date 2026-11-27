'use client';

import { useEffect, useState } from 'react';
import { BrandedLogin } from './BrandedLogin';
import { isTenantKey } from './branding';

/** Build-time switch, off by default. The real login at /login/ ignores the query string entirely (ADR-0007). */
export const previewEnabled = () => process.env.NEXT_PUBLIC_LOGIN_PREVIEW === '1';

/** DEV ONLY: shows the look of a fixture tenant chosen by `?tenant=`. Renders nothing unless the flag is set. */
export function LoginPreview() {
  const [key, setKey] = useState<string | undefined>();
  const enabled = previewEnabled();
  useEffect(() => {
    if (!enabled) return;
    const k = new URLSearchParams(window.location.search).get('tenant');
    setKey(isTenantKey(k) ? k : undefined);
  }, [enabled]);
  return enabled ? <BrandedLogin tenantKey={key} /> : null;
}
