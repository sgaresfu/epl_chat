/**
 * A club crest: a solid colour disc with a three-letter monogram.
 *
 * The colour and its text colour both come from the API's canonical club
 * table, so light-shirted clubs get dark monograms and every crest meets
 * contrast without a per-club special case in the CSS.
 */

import type { Club } from '@/api/types'

interface Props {
  club: Club
  size?: number
}

export function Crest({ club, size = 32 }: Props) {
  return (
    <span
      className="crest"
      style={{
        width: size,
        height: size,
        background: club.primary,
        color: club.on_primary,
        fontSize: Math.round(size * 0.3),
      }}
      aria-hidden="true"
    >
      {club.short_name}
    </span>
  )
}
