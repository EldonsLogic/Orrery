/**
 * Incremental Server-Sent Events parser (WEB-026, ADR-0044 item 9). Only `data:` fields are read; `event`,
 * `id`, `retry` and comments are ignored, so the server cannot steer the client with them. Size caps make a
 * hostile or broken stream fail instead of growing memory.
 */
export const MAX_SSE_LINE = 512 * 1024;
export const MAX_SSE_DATA = 256 * 1024;

export class SseError extends Error {}

export class SseParser {
  private buf = '';
  private data: string[] = [];
  private dataLen = 0;

  /** Feed decoded text; returns the data payload of every event completed by it. */
  push(chunk: string, final = false): string[] {
    this.buf += chunk;
    const out: string[] = [];
    let i = 0;
    for (;;) {
      const m = /\r\n|\n|\r/.exec(this.buf.slice(i, i + MAX_SSE_LINE + 2));
      if (!m) {
        if (this.buf.length - i > MAX_SSE_LINE) throw new SseError('line too long');
        break;
      }
      // A lone CR at the very end may be the first half of CRLF: wait for the next chunk.
      if (!final && m[0] === '\r' && i + m.index + 1 === this.buf.length) break;
      const line = this.buf.slice(i, i + m.index);
      i += m.index + m[0].length;
      this.line(line, out);
    }
    this.buf = this.buf.slice(i);
    return out;
  }

  /** The stream closed: release a held trailing CR. An unfinished event is discarded, never dispatched. */
  end(): string[] {
    return this.push('', true);
  }

  private line(line: string, out: string[]): void {
    if (line === '') {
      if (this.data.length) out.push(this.data.join('\n'));
      this.data = [];
      this.dataLen = 0;
      return;
    }
    if (line.startsWith(':')) return;
    const c = line.indexOf(':');
    const field = c === -1 ? line : line.slice(0, c);
    if (field !== 'data') return;
    let value = c === -1 ? '' : line.slice(c + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    this.dataLen += value.length + 1;
    if (this.dataLen > MAX_SSE_DATA) throw new SseError('event too large');
    this.data.push(value);
  }
}
