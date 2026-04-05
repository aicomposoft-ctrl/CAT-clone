/**
 * Shared utility for API clients.
 */

/**
 * Strip undefined, null, and empty-string values from a params object
 * before passing to axios. Keeps numeric 0 and boolean false.
 */
export function cleanParams(obj: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  )
}

/** Escape a string for safe use in ECharts HTML formatter output */
export function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}
