/**
 * The hero headline, derived from where the season actually is.
 *
 * BRIEF section 6 is explicit that a stale hardcoded counter is worse than
 * none. The same applies to the sentence above it: "The season starts tonight"
 * is true for a few hours and wrong for the next nine months.
 */

import type { Home } from '@/api/types'

export function headline(home: Home | undefined): string {
  if (!home) return 'Prediction League'
  const { season, next_match: next } = home

  if (next.in_play) return 'It has started.'
  if (season.matches_played >= season.matches_total) return 'That is the season.'

  if (season.matches_played === 0) {
    const seconds = next.countdown_seconds
    if (seconds == null) return 'The season is nearly here.'
    if (seconds <= 0) return 'It has started.'
    const hours = seconds / 3600
    if (hours < 12) return 'The season starts tonight.'
    if (hours < 36) return 'The season starts tomorrow.'
    return `${Math.ceil(hours / 24)} days until the season starts.`
  }

  const n = season.matches_played
  return `${n} ${n === 1 ? 'match' : 'matches'} in.`
}
