// Small pure CSV reader and writer for WEB-024. No dependency, no browser access. .xlsx is NOT parsed here (see Q-179).
export type CsvParse = { rows: string[][]; error?: 'unterminatedQuote' };

const DELIMS = [',', ';', '\t'] as const;

/** Picks the delimiter that appears most in the first line outside quotes (comma wins ties). */
export function detectDelimiter(text: string): string {
  const counts = new Map<string, number>(DELIMS.map((d) => [d, 0]));
  let quoted = false;
  for (const ch of text) {
    if (ch === '"') quoted = !quoted;
    else if (!quoted && (ch === '\n' || ch === '\r')) break;
    else if (!quoted && counts.has(ch)) counts.set(ch, (counts.get(ch) ?? 0) + 1);
  }
  return DELIMS.reduce((best, d) => ((counts.get(d) ?? 0) > (counts.get(best) ?? 0) ? d : best), ',' as string);
}

/** RFC 4180 style: quotes, doubled quotes, CRLF or LF inside quotes, BOM stripped. Fully empty lines are dropped. */
export function parseCsv(input: string, delimiter?: string): CsvParse {
  const text = input.charCodeAt(0) === 0xfeff ? input.slice(1) : input;
  const d = delimiter ?? detectDelimiter(text);
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;
  let touched = false; // the current row has any character
  const endCell = () => { row.push(cell); cell = ''; };
  const endRow = () => {
    endCell();
    if (touched || row.some((c) => c !== '')) rows.push(row);
    row = []; touched = false;
  };
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]!;
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; } else quoted = false;
      } else cell += ch;
      continue;
    }
    if (ch === '"' && cell === '') { quoted = true; touched = true; }
    else if (ch === d) { endCell(); touched = true; }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      endRow();
    } else { cell += ch; touched = true; }
  }
  if (quoted) return { rows, error: 'unterminatedQuote' };
  if (touched || cell !== '') endRow();
  return { rows: rows.filter((r) => r.some((c) => c.trim() !== '')) };
}

const NUMBER = /^-?\d+(\.\d+)?$/;

/**
 * One cell for a CSV a person will open in a spreadsheet. A leading = + - @ tab or CR would run as a formula,
 * so the cell gets a leading apostrophe (plain numbers are left alone). Quotes when needed.
 */
export function csvCell(value: string): string {
  const safe = /^[=+\-@\t\r]/.test(value) && !NUMBER.test(value) ? `'${value}` : value;
  return /[",\n\r;]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
}

export const toCsv = (rows: ReadonlyArray<ReadonlyArray<string>>): string => rows.map((r) => r.map(csvCell).join(',')).join('\r\n') + '\r\n';
