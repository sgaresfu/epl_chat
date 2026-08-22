/**
 * What the four of them said about a club, in one line.
 *
 * A league table on its own is a league table — you can get one anywhere.
 * What this site has that nobody else does is four filed opinions about it,
 * so a row that says "all four have them 1st" or "COYG 3rd, BULBA 14th" is
 * the reason to look at *this* table rather than any other.
 *
 * Deliberately compares the predictions **to each other** rather than to the
 * live standings. Two matches into a season the table is noise, and
 * "TWZT had them 18th" printed beside a club sitting 2nd on goal difference
 * in August implies a verdict that has not been earned. Agreement and
 * disagreement between the four are true on day one and stay true in May.
 */

export interface Filed {
  person: string
  table: string[]
}

export interface Annotation {
  kind: 'consensus' | 'split'
  label: string
  /** Longer form for a title attribute, where the label has to stay short. */
  detail: string
}

const ORDINALS = ['th', 'st', 'nd', 'rd']

/** 1 -> "1st", 12 -> "12th", 23 -> "23rd". */
export function ordinal(n: number): string {
  const rem100 = n % 100
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`
  return `${n}${ORDINALS[n % 10] ?? 'th'}`
}

/**
 * A split is only worth printing when it is genuinely wide. Six places is
 * about the point where two people are describing different seasons — below
 * that everybody roughly agrees and the annotation is noise on every row.
 */
const SPLIT_THRESHOLD = 6

/** Where a Premier League season is actually decided. */
const TOP_BAND = 4
const DROP_BAND = 18

export function annotate(club: string, filed: Filed[]): Annotation | null {
  const placed = filed
    .map((f) => ({ person: f.person, at: f.table.indexOf(club) + 1 }))
    .filter((p) => p.at > 0)

  // One opinion is not a consensus and cannot be a split.
  if (placed.length < 2) return null

  const positions = placed.map((p) => p.at)
  const low = Math.min(...positions)
  const high = Math.max(...positions)

  if (low === high) {
    const who = placed.length === 4 ? 'All four' : `All ${placed.length}`
    return {
      kind: 'consensus',
      label: `${who} have them ${ordinal(low)}`,
      detail: `${placed.map((p) => p.person.toUpperCase()).join(', ')} all placed them ${ordinal(low)}.`,
    }
  }

  // Not unanimous on a position, but unanimous on the outcome. Four people
  // placing a club 19th, 20th, 20th and 20th are saying the same thing, and
  // "all four had them going down" is the more interesting sentence than
  // silence -- especially when that club is currently second.
  const who = placed.length === 4 ? 'All four' : `All ${placed.length}`
  if (high <= TOP_BAND) {
    return {
      kind: 'consensus',
      label: `${who} had them top four`,
      detail: `Placed between ${ordinal(low)} and ${ordinal(high)} by everyone who filed.`,
    }
  }
  if (low >= DROP_BAND) {
    return {
      kind: 'consensus',
      label: `${who} had them going down`,
      detail: `Placed between ${ordinal(low)} and ${ordinal(high)} by everyone who filed.`,
    }
  }

  if (high - low < SPLIT_THRESHOLD) return null

  const optimist = placed.find((p) => p.at === low)!
  const pessimist = placed.find((p) => p.at === high)!
  return {
    kind: 'split',
    label: `${optimist.person.toUpperCase()} ${ordinal(low)} · ${pessimist.person.toUpperCase()} ${ordinal(high)}`,
    detail: `${high - low} places between the highest and lowest call on this club.`,
  }
}

/**
 * The one line worth putting under a standings tile.
 *
 * Picks the widest disagreement across the whole table, because that is the
 * argument the four of them are actually having.
 */
export function widestSplit(filed: Filed[], clubName: (short: string) => string): string | null {
  if (filed.length < 2) return null

  const clubs = new Set(filed.flatMap((f) => f.table))
  let worst: { club: string; spread: number; low: number; high: number } | null = null

  for (const club of clubs) {
    const positions = filed.map((f) => f.table.indexOf(club) + 1).filter((n) => n > 0)
    if (positions.length < 2) continue
    const spread = Math.max(...positions) - Math.min(...positions)
    if (!worst || spread > worst.spread) {
      worst = { club, spread, low: Math.min(...positions), high: Math.max(...positions) }
    }
  }

  if (!worst || worst.spread < SPLIT_THRESHOLD) return null
  return `Widest disagreement: ${clubName(worst.club)}, ${ordinal(worst.low)} to ${ordinal(worst.high)}.`
}
