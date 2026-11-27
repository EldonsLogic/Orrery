'use client';

import { useSyncExternalStore } from 'react';

/** Phones (below the 48rem tablet breakpoint in styles/foundation.css). */
export const PHONE_QUERY = '(max-width: 47.9375rem)';

/** A media query as state. The server and the first paint report false; the browser value follows after hydration. */
export function useMedia(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const mq = window.matchMedia(query);
      mq.addEventListener('change', onChange);
      return () => mq.removeEventListener('change', onChange);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}
