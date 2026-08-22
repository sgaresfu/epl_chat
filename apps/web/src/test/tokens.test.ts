/**
 * The two dark blocks must declare the same tokens.
 *
 * Dark mode is expressed twice by necessity -- once for an explicit
 * `[data-theme="dark"]` choice and once inside `prefers-color-scheme` for
 * people who never chose -- because a media query cannot appear in a selector
 * list. Two copies drift: `--on-ink` was added to one and not the other, and
 * the symptom was white-on-white text for exactly the people who had not
 * touched the toggle, which is most of them.
 *
 * This asserts the two lists stay identical, so the next token added to one
 * fails here rather than in somebody's dark bedroom.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const css = readFileSync(join(__dirname, '../styles/tokens.css'), 'utf8')

/** Token names declared inside the block that follows `marker`. */
function tokensAfter(marker: string): string[] {
  const start = css.indexOf(marker)
  expect(start, `${marker} not found in tokens.css`).toBeGreaterThan(-1)
  // The block ends at the first closing brace at the start of a line.
  const rest = css.slice(start)
  const end = rest.search(/\n\s*}\n/)
  const body = rest.slice(0, end === -1 ? undefined : end)
  return [...body.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1] as string).sort()
}

describe('theme tokens', () => {
  const explicit = tokensAfter(':root[data-theme="dark"]')
  const system = tokensAfter(':root:not([data-theme="light"])')

  it('both dark blocks declare the same token names', () => {
    expect(system).toEqual(explicit)
  })

  it('declares a meaningful number of them, so an empty match cannot pass', () => {
    expect(explicit.length).toBeGreaterThan(15)
  })

  it('every dark token is also defined in the light root', () => {
    const root = tokensAfter(':root {')
    for (const token of explicit) expect(root).toContain(token)
  })

  it('text on an ink-filled ground inverts, unlike text on blue', () => {
    // --on-accent sits on blue and club colours, which are identical in both
    // themes, so it stays white. --on-ink sits on --ink, which flips.
    expect(explicit).toContain('--on-ink')
    expect(css).toMatch(/--on-ink:\s*#ffffff/)
    expect(css).toMatch(/--on-ink:\s*#000000/)
  })
})
