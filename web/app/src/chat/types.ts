/**
 * Chat view-model types (WEB-004). The event shapes follow ADR-0044 (AG-UI as transport, allow-listed
 * events only) and the documented OPR-010 stream; the real stream client is WEB-026. Nothing here is
 * authority: a mode or an event never grants access, the server decides with the caller's own roles.
 */
export const MODES = ['discover', 'ask', 'act', 'change'] as const;
export type ChatMode = (typeof MODES)[number];
/** Modes that write or alter the business and so need a confirmation step. */
export const needsConfirmation = (m: ChatMode): boolean => m === 'act' || m === 'change';

export const RISKS = ['R0', 'R1', 'R2', 'R3', 'R4'] as const;
export type RiskClass = (typeof RISKS)[number];
export type ToolOutcome = 'ok' | 'denied' | 'error' | 'pending_approval';

/** One field change. `field` (a Blueprint field id, or `state`) lets the screen show the label and values in the reader's language; `label` is the fallback. */
export type ChangeLine = { field?: string; label: string; before: string; after: string };
/** A record an answer was drawn from (WEB-029). Shown as a chip that opens the record; the record screen re-checks access. */
export type SourceRef = { entity: string; id: string };
export const MAX_SOURCES = 10;

/** The only events the screen reacts to; anything else is dropped (fail closed). */
export type ChatEvent =
  | { type: 'run_started'; runId: string }
  | { type: 'text_delta'; messageId: string; delta: string }
  | { type: 'text_end'; messageId: string }
  | { type: 'sources'; messageId: string; records: ReadonlyArray<SourceRef> }
  | { type: 'tool_call'; callId: string; tool: string; risk: RiskClass }
  | { type: 'tool_result'; callId: string; outcome: ToolOutcome }
  | { type: 'confirm_required'; confirmId: string; tool: string; risk: RiskClass; changes: ReadonlyArray<ChangeLine>; record?: SourceRef }
  | { type: 'approval_pending'; approvalId: string; tool: string; risk: RiskClass; record?: SourceRef }
  | { type: 'abstain'; clarifyKey: string }
  | { type: 'run_error'; code: string }
  | { type: 'run_finished'; outcome: 'done' | 'interrupt' | 'cancelled' };

export type SendRequest = { text: string; mode: ChatMode };
export type ConfirmDecision = { confirmId: string; accepted: boolean };

/** What the screen needs from a chat backend. The real AG-UI client (WEB-026) implements it. */
export interface ChatPort {
  send(req: SendRequest): void;
  cancel(): void;
  /** Answer a confirmation card. This is NOT an approval: approvals are decided in the inbox. */
  respond(decision: ConfirmDecision): void;
  /** Returns an unsubscribe function. */
  subscribe(listener: (event: ChatEvent) => void): () => void;
}

export type ChatRole = 'user' | 'assistant' | 'system';
export type ChatMessage = { id: string; role: ChatRole; text: string; streaming: boolean; sources?: ReadonlyArray<SourceRef> };
export type ActivityStep = { callId: string; tool: string; risk: RiskClass; outcome: ToolOutcome | 'running' };
export type PendingConfirm = { confirmId: string; tool: string; risk: RiskClass; changes: ReadonlyArray<ChangeLine>; record?: SourceRef };
export type PendingApproval = { approvalId: string; tool: string; risk: RiskClass; record?: SourceRef };

export type ChatState = {
  mode: ChatMode;
  run: 'idle' | 'running' | 'cancelling';
  messages: ReadonlyArray<ChatMessage>;
  activity: ReadonlyArray<ActivityStep>;
  confirm: PendingConfirm | null;
  approvals: ReadonlyArray<PendingApproval>;
  clarifyKey: string | null;
  errorCode: string | null;
};

export const MAX_MESSAGE_LENGTH = 4000;
