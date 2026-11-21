/**
 * Untrusted text is shown as plain text only. React escapes markup, so a script tag is displayed, not run; this file
 * handles what escaping does not: control and bidirectional characters (a right-to-left override can reorder text
 * around it and fake a different value) are replaced by a visible marker, and very long text is cut.
 */
const MAX = 2000;

function hostile(cp: number): boolean {
  if (cp === 0x09 || cp === 0x0a) return false; // tab and newline are fine
  return (
    cp <= 0x1f ||
    (cp >= 0x7f && cp <= 0x9f) ||
    (cp >= 0x200b && cp <= 0x200f) || // zero width and the LRM, RLM marks
    cp === 0x2028 ||
    cp === 0x2029 ||
    (cp >= 0x202a && cp <= 0x202e) || // embeddings and overrides
    (cp >= 0x2060 && cp <= 0x206f) || // word joiner, isolates, deprecated formatting
    cp === 0xfeff ||
    (cp >= 0xfff9 && cp <= 0xfffb) ||
    (cp >= 0xe0000 && cp <= 0xe007f) // tag characters
  );
}

/** Any value to a safe display string. Non-strings are never trusted to have a useful toString. */
export function plainText(value: unknown, max: number = MAX): string {
  let s: string;
  if (typeof value === 'string') s = value;
  else if (typeof value === 'number' || typeof value === 'boolean') s = String(value);
  else if (value === null || value === undefined) s = '';
  else {
    try {
      s = JSON.stringify(value) ?? '';
    } catch {
      s = '';
    }
  }
  let out = '';
  let n = 0;
  for (const ch of s) {
    if (n++ >= max) return `${out}…`;
    const cp = ch.codePointAt(0) ?? 0;
    out += hostile(cp) ? `<U+${cp.toString(16).toUpperCase().padStart(4, '0')}>` : ch;
  }
  return out;
}

export const asList = <T,>(v: ReadonlyArray<T> | null | undefined): ReadonlyArray<T> => (Array.isArray(v) ? v : []);

/** `key: value` lines of an event detail, as text. Nothing nested is expanded beyond JSON text. */
export function detailLines(detail: unknown): string[] {
  if (!detail || typeof detail !== 'object' || Array.isArray(detail)) return [];
  return Object.entries(detail as Record<string, unknown>)
    .slice(0, 12)
    .map(([k, v]) => `${plainText(k, 40)}: ${plainText(v, 200)}`);
}
