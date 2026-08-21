import { describe, expect, it } from 'vitest'
import { countdown, countdownWords, signed } from '@/lib/format'

describe('countdown', () => {
  it('formats as H:MM:SS like the design', () => {
    expect(countdown(4 * 3600 + 12 * 60 + 8)).toBe('4:12:08')
  })

  it('pads minutes and seconds', () => {
    expect(countdown(3601)).toBe('1:00:01')
  })

  it('never goes negative once the match has started', () => {
    expect(countdown(-500)).toBe('0:00:00')
  })

  it('counts past 24 hours rather than wrapping', () => {
    // A 30-hour countdown must not display as 6 hours.
    expect(countdown(30 * 3600)).toBe('30:00:00')
  })
})

describe('countdownWords', () => {
  it('describes days when there are days left', () => {
    expect(countdownWords(2 * 86400 + 3 * 3600)).toBe('2 days, 3 hours')
  })

  it('uses the singular correctly', () => {
    expect(countdownWords(86400 + 3600)).toBe('1 day, 1 hour')
  })

  it('falls back to minutes in the final hour', () => {
    expect(countdownWords(300)).toBe('5 minutes')
  })
})

describe('signed', () => {
  it('prefixes a plus on a positive goal difference', () => {
    expect(signed(6)).toBe('+6')
  })

  it('uses a real minus sign so figures align in tabular numerals', () => {
    expect(signed(-4)).toBe('−4')
    expect(signed(-4)).not.toBe('-4')
  })

  it('renders zero without a sign', () => {
    expect(signed(0)).toBe('0')
  })
})
