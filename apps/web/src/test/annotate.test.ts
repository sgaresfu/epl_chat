import { describe, expect, it } from 'vitest'
import { annotate, ordinal, widestSplit, type Filed } from '@/lib/annotate'

/** Four tables that differ in known, deliberate ways. */
const FILED: Filed[] = [
  { person: 'coyg', table: ['ARS', 'MCI', 'LIV', 'CHE', 'MUN', 'TOT', 'NEW', 'BHA', 'AVL', 'EVE', 'FUL', 'BRE', 'CRY', 'NFO', 'SUN', 'LEE', 'BOU', 'IPS', 'HUL', 'COV'] },
  { person: 'aure', table: ['ARS', 'MCI', 'CHE', 'LIV', 'TOT', 'MUN', 'BHA', 'NEW', 'AVL', 'EVE', 'FUL', 'BRE', 'CRY', 'NFO', 'SUN', 'LEE', 'BOU', 'COV', 'IPS', 'HUL'] },
  { person: 'twzt', table: ['ARS', 'CHE', 'LIV', 'MCI', 'MUN', 'TOT', 'NEW', 'BHA', 'AVL', 'EVE', 'FUL', 'BRE', 'CRY', 'NFO', 'SUN', 'BOU', 'LEE', 'COV', 'IPS', 'HUL'] },
  { person: 'bulba', table: ['ARS', 'MUN', 'MCI', 'CHE', 'LIV', 'TOT', 'NEW', 'BHA', 'AVL', 'EVE', 'FUL', 'BRE', 'CRY', 'NFO', 'SUN', 'LEE', 'BOU', 'COV', 'IPS', 'HUL'] },
]

describe('ordinal', () => {
  it('handles the ordinary cases', () => {
    expect(ordinal(1)).toBe('1st')
    expect(ordinal(2)).toBe('2nd')
    expect(ordinal(3)).toBe('3rd')
    expect(ordinal(4)).toBe('4th')
    expect(ordinal(20)).toBe('20th')
  })

  it('handles the teens, which do not follow the rule', () => {
    expect(ordinal(11)).toBe('11th')
    expect(ordinal(12)).toBe('12th')
    expect(ordinal(13)).toBe('13th')
  })
})

describe('annotate', () => {
  it('reports a unanimous call', () => {
    const a = annotate('ARS', FILED)
    expect(a).not.toBeNull()
    expect(a!.kind).toBe('consensus')
    expect(a!.label).toBe('All four have them 1st')
  })

  it('says nothing about a narrow spread in mid-table', () => {
    // NEW: 7th, 8th, 7th, 7th. Not one agreed position, not inside either
    // band, and nowhere near a six-place split -- nothing worth printing.
    expect(annotate('NEW', FILED)).toBeNull()
  })

  it('prints a split once it is genuinely wide', () => {
    const wide: Filed[] = [
      { person: 'coyg', table: ['BHA', 'A', 'B', 'C', 'D', 'E', 'F', 'ARS'] },
      { person: 'bulba', table: ['ARS', 'A', 'B', 'C', 'D', 'E', 'F', 'BHA'] },
    ]
    const a = annotate('BHA', wide)
    expect(a).not.toBeNull()
    expect(a!.kind).toBe('split')
    expect(a!.label).toBe('COYG 1st · BULBA 8th')
    expect(a!.detail).toContain('7 places')
  })

  it('treats a shared verdict on relegation as a consensus', () => {
    // COV: 20th, 18th, 18th, 18th. Not one agreed position, but one agreed
    // outcome -- and that is the sentence worth printing.
    const a = annotate('COV', FILED)
    expect(a).not.toBeNull()
    expect(a!.kind).toBe('consensus')
    expect(a!.label).toBe('All four had them going down')
  })

  it('says nothing about a club nobody placed', () => {
    expect(annotate('NOT-A-CLUB', FILED)).toBeNull()
  })

  it('needs at least two opinions before it claims a consensus', () => {
    expect(annotate('ARS', [FILED[0]!])).toBeNull()
  })

  it('counts only the people who actually placed the club', () => {
    const partial: Filed[] = [
      { person: 'coyg', table: ['ARS'] },
      { person: 'aure', table: ['ARS'] },
      { person: 'twzt', table: [] },
      { person: 'bulba', table: [] },
    ]
    const a = annotate('ARS', partial)
    expect(a!.label).toBe('All 2 have them 1st')
  })

  it('is stable regardless of the order the tables arrive in', () => {
    const forward = annotate('ARS', FILED)
    const backward = annotate('ARS', [...FILED].reverse())
    expect(backward!.label).toBe(forward!.label)
  })
})

describe('widestSplit', () => {
  const name = (s: string) => s

  it('finds the club the four disagree about most', () => {
    const wide: Filed[] = [
      { person: 'coyg', table: ['BHA', 'A', 'B', 'C', 'D', 'E', 'F', 'ARS'] },
      { person: 'bulba', table: ['ARS', 'A', 'B', 'C', 'D', 'E', 'F', 'BHA'] },
    ]
    const line = widestSplit(wide, name)
    expect(line).toContain('BHA')
    expect(line).toContain('1st to 8th')
  })

  it('says nothing when the four broadly agree', () => {
    expect(widestSplit(FILED, name)).toBeNull()
  })

  it('says nothing with fewer than two tables', () => {
    expect(widestSplit([FILED[0]!], name)).toBeNull()
  })

  it('renders the club through the naming function it is given', () => {
    const wide: Filed[] = [
      { person: 'a', table: ['BHA', 'A', 'B', 'C', 'D', 'E', 'F', 'X'] },
      { person: 'b', table: ['X', 'A', 'B', 'C', 'D', 'E', 'F', 'BHA'] },
    ]
    expect(widestSplit(wide, (s) => (s === 'BHA' ? 'Brighton' : s))).toContain('Brighton')
  })
})

describe('band consensus', () => {
  it('reports a unanimous relegation call even when the exact places differ', () => {
    // The real case: Hull went 19th, 20th, 20th, 20th across the four tables
    // and are currently second. A spread of one is not unanimity, but the
    // verdict is identical and it is the most interesting line on the page.
    const drop: Filed[] = [
      { person: 'coyg', table: [...Array(18).fill('X').map((_, i) => `C${i}`), 'HUL', 'COV'] },
      { person: 'aure', table: [...Array(18).fill('X').map((_, i) => `C${i}`), 'COV', 'HUL'] },
      { person: 'twzt', table: [...Array(18).fill('X').map((_, i) => `C${i}`), 'COV', 'HUL'] },
      { person: 'bulba', table: [...Array(18).fill('X').map((_, i) => `C${i}`), 'COV', 'HUL'] },
    ]
    const a = annotate('HUL', drop)
    expect(a).not.toBeNull()
    expect(a!.kind).toBe('consensus')
    expect(a!.label).toBe('All four had them going down')
    expect(a!.detail).toContain('19th')
  })

  it('reports a unanimous top-four call', () => {
    const top: Filed[] = [
      { person: 'coyg', table: ['ARS', 'MCI', 'LIV', 'CHE'] },
      { person: 'aure', table: ['MCI', 'ARS', 'CHE', 'LIV'] },
      { person: 'twzt', table: ['LIV', 'CHE', 'ARS', 'MCI'] },
      { person: 'bulba', table: ['CHE', 'LIV', 'MCI', 'ARS'] },
    ]
    const a = annotate('ARS', top)
    expect(a!.label).toBe('All four had them top four')
  })

  it('still prefers an exact unanimous position over the band', () => {
    const exact: Filed[] = [
      { person: 'a', table: ['ARS', 'B', 'C', 'D'] },
      { person: 'b', table: ['ARS', 'B', 'C', 'D'] },
    ]
    expect(annotate('ARS', exact)!.label).toBe('All 2 have them 1st')
  })

  it('says nothing about a club everyone put mid-table', () => {
    const mid: Filed[] = [
      { person: 'a', table: [...Array(9).fill(0).map((_, i) => `C${i}`), 'FUL', 'X'] },
      { person: 'b', table: [...Array(10).fill(0).map((_, i) => `C${i}`), 'FUL'] },
    ]
    expect(annotate('FUL', mid)).toBeNull()
  })
})
