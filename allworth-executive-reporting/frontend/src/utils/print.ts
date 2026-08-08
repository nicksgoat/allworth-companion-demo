/**
 * Lightweight print helper — opens a branded, print-ready window with a table.
 *
 * Used by the Bond Ladder monitor and Account Lookup views so advisors can
 * print (or "Save as PDF") a clean report without the app chrome. Rendering a
 * standalone document avoids the virtualized-table problem where only the
 * on-screen rows would otherwise print.
 */

export interface PrintColumn<T> {
  header: string;
  value: (row: T) => string;
  align?: 'left' | 'right' | 'center';
}

export interface PrintReportOptions<T> {
  title: string;
  subtitle?: string;
  /** Small key/value pairs rendered under the header (filters, totals, etc.). */
  meta?: { label: string; value: string }[];
  columns: PrintColumn<T>[];
  rows: T[];
}

const escapeHtml = (value: string): string =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

export function printReport<T>(options: PrintReportOptions<T>): void {
  const { title, subtitle, meta = [], columns, rows } = options;

  const win = window.open('', '_blank', 'noopener,noreferrer,width=1100,height=800');
  if (!win) {
    // Popup blocked — fall back to printing the current page.
    window.print();
    return;
  }

  const headerCells = columns
    .map(col => `<th style="text-align:${col.align ?? 'left'}">${escapeHtml(col.header)}</th>`)
    .join('');

  const bodyRows = rows
    .map(row => {
      const cells = columns
        .map(col => `<td style="text-align:${col.align ?? 'left'}">${escapeHtml(col.value(row))}</td>`)
        .join('');
      return `<tr>${cells}</tr>`;
    })
    .join('');

  const metaHtml = meta.length
    ? `<div class="meta">${meta
        .map(m => `<span><b>${escapeHtml(m.label)}:</b> ${escapeHtml(m.value)}</span>`)
        .join('')}</div>`
    : '';

  const printedAt = new Date().toLocaleString();

  const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>${escapeHtml(title)}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Lato', Arial, sans-serif; color: #1a2733; margin: 24px; }
  .brand { color: #173D67; font-weight: 800; letter-spacing: 0.5px; text-transform: uppercase; font-size: 11px; }
  h1 { color: #0C2E4E; font-size: 20px; margin: 2px 0 2px; }
  .subtitle { color: #5b6b7b; font-size: 12px; margin: 0 0 10px; }
  .meta { display: flex; flex-wrap: wrap; gap: 14px; font-size: 11px; color: #5b6b7b; margin-bottom: 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 10.5px; }
  thead th { background: #173D67; color: #fff; padding: 6px 8px; border: 1px solid #173D67; white-space: nowrap; }
  tbody td { padding: 4px 8px; border: 1px solid #d9e0e7; }
  tbody tr:nth-child(even) { background: #f5f7fa; }
  .footer { margin-top: 14px; font-size: 10px; color: #9aa7b4; }
  @media print { body { margin: 12mm; } thead { display: table-header-group; } tr { break-inside: avoid; } }
</style>
</head>
<body>
  <div class="brand">Allworth Financial</div>
  <h1>${escapeHtml(title)}</h1>
  ${subtitle ? `<p class="subtitle">${escapeHtml(subtitle)}</p>` : ''}
  ${metaHtml}
  <table>
    <thead><tr>${headerCells}</tr></thead>
    <tbody>${bodyRows}</tbody>
  </table>
  <div class="footer">${rows.length.toLocaleString()} row(s) · Printed ${escapeHtml(printedAt)}</div>
</body>
</html>`;

  win.document.open();
  win.document.write(html);
  win.document.close();
  win.focus();
  // Give the new document a tick to lay out before invoking print.
  setTimeout(() => {
    win.print();
  }, 250);
}
