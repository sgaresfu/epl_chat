/**
 * Light / dark / system, as a three-way segmented control.
 *
 * Three states, not a two-way switch: "system" is the default and the right
 * answer for most people, and a binary toggle silently discards it the first
 * time anyone touches the control.
 */

import { useEffect, useState } from 'react'
import { applyTheme, readTheme, type Theme } from '@/lib/theme'

const OPTIONS: ReadonlyArray<[Theme, string, string]> = [
  ['light', 'Light', 'M12 4.5v-2M12 21.5v-2M4.5 12h-2M21.5 12h-2M6.7 6.7 5.3 5.3M18.7 18.7l-1.4-1.4M6.7 17.3l-1.4 1.4M18.7 5.3l-1.4 1.4'],
  ['system', 'System', ''],
  ['dark', 'Dark', 'M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z'],
]

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('system')

  // Read on mount rather than in useState's initialiser: the pre-paint script
  // in index.html has already stamped the element, and this only has to catch
  // up with it.
  useEffect(() => setTheme(readTheme()), [])

  const choose = (next: Theme) => {
    setTheme(next)
    applyTheme(next)
  }

  return (
    <div className="theme" role="group" aria-label="Colour theme">
      {OPTIONS.map(([value, label, path]) => (
        <button
          key={value}
          type="button"
          className="theme__opt"
          aria-pressed={theme === value}
          aria-label={label}
          title={label}
          onClick={() => choose(value)}
        >
          {path ? (
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              aria-hidden="true"
            >
              {value === 'light' && <circle cx="12" cy="12" r="4" />}
              <path d={path} />
            </svg>
          ) : (
            <span className="theme__auto" aria-hidden="true">
              A
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
