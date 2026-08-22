/**
 * Theme: system by default, overridable, remembered.
 *
 * Three states rather than two. "system" is the default and follows the OS,
 * which is what most people want and never think about; the two explicit
 * choices exist for the person whose phone is in dark mode but who wants the
 * table on white. Storing "system" as an absent key rather than a value keeps
 * the pre-paint script in index.html to three lines.
 */

export type Theme = 'system' | 'light' | 'dark'

const KEY = 'theme'

export function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(KEY)
    return stored === 'dark' || stored === 'light' ? stored : 'system'
  } catch {
    // Private mode, or storage disabled entirely.
    return 'system'
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement
  if (theme === 'system') delete root.dataset.theme
  else root.dataset.theme = theme

  try {
    if (theme === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, theme)
  } catch {
    // The theme still applies for this session; it just will not persist.
  }
}

/** What the user actually sees right now, with "system" resolved. */
export function resolvedTheme(theme: Theme): 'light' | 'dark' {
  if (theme !== 'system') return theme
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}
