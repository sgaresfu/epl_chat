import { describe, expect, it } from 'vitest'
import { fold } from '@/lib/fold'

describe('fold', () => {
  it('makes diacritics searchable without them', () => {
    // The same bug the Python side had: Ø carries no combining mark, so NFD
    // leaves it whole and a naive filter deletes it.
    expect(fold('Ødegaard')).toBe(fold('Odegaard'))
    expect(fold('Magalhães')).toBe(fold('Magalhaes'))
    expect(fold('Gyökeres')).toBe(fold('Gyokeres'))
  })

  it('does not swallow the leading letter of Ødegaard', () => {
    expect(fold('Ødegaard')).toBe('odegaard')
    expect(fold('Ødegaard')).not.toBe('degaard')
  })

  it('ignores apostrophes so "nottm" finds the club', () => {
    expect(fold("Nott'm Forest")).toBe('nottm forest')
    expect(fold('NOTTM FOREST')).toBe('nottm forest')
  })

  it('expands ampersands', () => {
    expect(fold('Brighton & Hove Albion')).toBe(fold('Brighton and Hove Albion'))
  })

  it('handles an empty string', () => {
    expect(fold('')).toBe('')
  })
})
