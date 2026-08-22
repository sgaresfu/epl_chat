/**
 * "1 quotes · 1 bets" appeared on the group page, "1 matches in." on the home
 * page, "1 matches played" in the line of the day. Three separate places got
 * the same thing wrong, so counting and labelling now happen together.
 */
export function plural(count: number, singular: string, pluralForm?: string): string {
  return `${count} ${count === 1 ? singular : (pluralForm ?? `${singular}s`)}`
}
