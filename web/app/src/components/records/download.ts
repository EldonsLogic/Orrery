// Browser-only helper: offers CSV text as a file. The text is built by the pure models; nothing is uploaded.
export function downloadCsv(fileName: string, text: string): void {
  const url = URL.createObjectURL(new Blob(['﻿', text], { type: 'text/csv;charset=utf-8' })); // BOM so spreadsheets read Arabic
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  a.click();
  URL.revokeObjectURL(url);
}
