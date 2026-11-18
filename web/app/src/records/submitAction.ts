// The single write path for the record screens. PLACEHOLDER: waiting for the tool API gateway (PLT-009).
// It returns a fixed result. It never stores, logs, sends or even reads `values`: nothing leaves the page.
import { executable, type ActionModel } from './actions';

export type SubmitRequest = {
  entityId: string;
  recordId?: string;
  action: ActionModel;
  /** Typed for the future gateway call; deliberately unused here. */
  values: Readonly<Record<string, string>>;
};
export type SubmitResult = { status: 'waiting_for_gateway' } | { status: 'refused' };

// TODO(PLT-009): replace the body with the gateway call (idempotency key, caller from the session, audit id).
export async function submitAction(request: SubmitRequest): Promise<SubmitResult> {
  if (!executable(request.action)) return { status: 'refused' }; // R3/R4 and non-agent-creatable: never run by the UI
  return { status: 'waiting_for_gateway' };
}
