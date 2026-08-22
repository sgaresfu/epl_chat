/**
 * Three separate places shipped "1 matches": the hero, the line of the day and
 * the group page's summary. Counting and labelling now happen in one function.
 */
import { describe, expect, it } from 'vitest'
import { plural } from '@/lib/plural'

describe('plural', () => {
  it('uses the singular for one', () => {
    expect(plural(1, 'quote')).toBe('1 quote')
    expect(plural(1, 'bet')).toBe('1 bet')
    expect(plural(1, 'match', 'matches')).toBe('1 match')
  })

  it('uses the plural for none', () => {
    expect(plural(0, 'quote')).toBe('0 quotes')
  })

  it('uses the plural for many', () => {
    expect(plural(7, 'quote')).toBe('7 quotes')
  })

  it('takes an irregular plural when the default would be wrong', () => {
    expect(plural(3, 'entry', 'entries')).toBe('3 entries')
    expect(plural(3, 'match', 'matches')).toBe('3 matches')
  })
})
