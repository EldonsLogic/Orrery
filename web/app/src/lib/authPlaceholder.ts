/**
 * PLACEHOLDER until PLT-005 (identity service). Nothing here authenticates anyone, calls a
 * network, stores or logs a credential. Each handler returns a fixed result so the pages can be
 * built and reviewed. Replace the bodies (not the types) when the identity service exists.
 */
export type AuthResult = { ok: true } | { ok: false };

export type LoginInput = { email: string; password: string };
export type ResetRequestInput = { email: string };
export type ResetConfirmInput = { password: string };

export type LoginHandler = (input: LoginInput) => Promise<AuthResult>;
export type ResetRequestHandler = (input: ResetRequestInput) => Promise<AuthResult>;
export type ResetConfirmHandler = (input: ResetConfirmInput) => Promise<AuthResult>;

/** Always fails, with one generic outcome: the wording never says whether the account exists. */
export const placeholderLogin: LoginHandler = async () => ({ ok: false });

/** Always succeeds, so the page shows the same text whether or not the email has an account. */
export const placeholderResetRequest: ResetRequestHandler = async () => ({ ok: true });

export const placeholderResetConfirm: ResetConfirmHandler = async () => ({ ok: true });
