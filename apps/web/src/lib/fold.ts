/**
 * Fold a name for searching.
 *
 * Mirrors `normalise` in shared/clubs.py: strip diacritics so "Odegaard"
 * finds "Ødegaard", and drop punctuation so "nottm" finds "Nott'm Forest".
 * Used for matching only -- display always keeps the original characters.
 *
 * Ø, Đ and friends carry no combining mark, so NFD leaves them intact and a
 * naive alphanumeric filter deletes them outright. They are transliterated
 * explicitly, which is the same bug the Python side had to fix.
 */

const ATOMIC: Record<string, string> = {
  ø: 'o',
  đ: 'd',
  ð: 'd',
  ł: 'l',
  ß: 'ss',
  æ: 'ae',
  œ: 'oe',
  þ: 'th',
}

export function fold(value: string): string {
  return value
    .toLowerCase()
    .replace(/[øđðłßæœþ]/g, (ch) => ATOMIC[ch] ?? ch)
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/['’.]/g, '')
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
}
