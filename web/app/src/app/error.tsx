'use client';

import { ErrorView } from '../components/auth/ErrorView';

/** The error object is deliberately not shown or logged here: no detail reaches the customer. */
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <ErrorView kind="generic" onRetry={reset} />;
}
