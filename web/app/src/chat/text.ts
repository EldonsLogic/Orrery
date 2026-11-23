// Bidi override/embedding controls (U+202A..202E) and isolates (U+2066..2069) can reorder the text
// around them; C0 controls (except tab and newline), DEL, zero-width characters and BOM are invisible.
// Removed from user and model text; each message is then rendered isolated.
const dropped = (c: number): boolean =>
  (c >= 0x202a && c <= 0x202e) ||
  (c >= 0x2066 && c <= 0x2069) ||
  (c < 0x20 && c !== 0x09 && c !== 0x0a) ||
  c === 0x7f ||
  c === 0x200b ||
  c === 0x2060 ||
  c === 0xfeff;

export const plainText = (s: string): string => Array.from(s).filter((ch) => !dropped(ch.codePointAt(0) as number)).join('');

export type ComposerKey = { key: string; shiftKey: boolean; isComposing?: boolean; keyCode?: number };
/** Enter sends, Shift+Enter is a newline, and nothing sends while an IME is composing. */
export function composerKeyAction(e: ComposerKey): 'send' | 'none' {
  if (e.key !== 'Enter' || e.shiftKey) return 'none';
  if (e.isComposing || e.keyCode === 229) return 'none';
  return 'send';
}

/** Language of a text by script: Arabic only -> 'ar', Latin only -> 'en', mixed or neither -> undefined (inherit). For `lang` (WCAG 3.1.2). */
export function textLang(text: string): 'ar' | 'en' | undefined {
  const ar = /[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFC]/.test(text);
  const en = /[A-Za-z]/.test(text);
  return ar && !en ? 'ar' : en && !ar ? 'en' : undefined;
}
