/**
 * The hero headline is computed, never written down.
 *
 * A hardcoded "The season starts tonight." is correct for a few hours and
 * wrong for the following nine months, which is exactly the failure the brief
 * calls out for the season counters.
 */

import { describe, expect, it } from 'vitest'
import type { Home, Season } from '@/api/types'

// Re-implemented import target: the function is exported for test from Home.tsx
import { headline } from '@/lib/headline'

function season(over: Partial<Season> = {}): Season {
  return {
    starts: '2026-08-21T19:00:00Z', ends: '2027-05-30T15:00:00Z', today: '2026-08-21T16:00:00Z',
    percent: 0, day: 1, total_days: 282, days_remaining: 282,
    gameweeks_played: 0, gameweeks_total: 38,
    matches_played: 0, matches_total: 380, matches_remaining: 380,
    watched: 0, markers: [], ...over,
  }
}

function home(over: Partial<Home> = {}, seasonOver: Partial<Season> = {}): Home {
  return {
    next_match: { fixture: null, countdown_seconds: 3600, in_play: false, message: null },
    season: season(seasonOver),
    line_of_the_day: null,
    ...over,
  }
}

describe('headline', () => {
  it('says tonight when the first match is hours away', () => {
    expect(headline(home({ next_match: { fixture: null, countdown_seconds: 2 * 3600, in_play: false, message: null } })))
      .toBe('The season starts tonight.')
  })

  it('says tomorrow when the first match is a day out', () => {
    expect(headline(home({ next_match: { fixture: null, countdown_seconds: 20 * 3600, in_play: false, message: null } })))
      .toBe('The season starts tomorrow.')
  })

  it('counts the days when the season is still a week away', () => {
    expect(headline(home({ next_match: { fixture: null, countdown_seconds: 7 * 86400, in_play: false, message: null } })))
      .toBe('7 days until the season starts.')
  })

  it('changes the moment a match is in play', () => {
    expect(headline(home({ next_match: { fixture: null, countdown_seconds: 0, in_play: true, message: null } })))
      .toBe('It has started.')
  })

  it('reports progress once matches have been played', () => {
    expect(headline(home({}, { matches_played: 42 }))).toBe('42 matches in.')
  })

  it('closes the season out on the final day', () => {
    expect(headline(home({}, { matches_played: 380, matches_total: 380 }))).toBe('That is the season.')
  })

  it('degrades to the site name before anything has loaded', () => {
    expect(headline(undefined)).toBe('Prediction League')
  })
})
