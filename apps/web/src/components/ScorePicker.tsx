/**
 * Calling a scoreline, in as few taps as possible.
 *
 * Two steppers rather than a text field: on a phone a number input summons a
 * keyboard for something that is almost always 0, 1 or 2, and a keyboard over
 * a fixture list is a worse experience than two buttons. Both remain fully
 * operable from a keyboard, and the whole control is one labelled group so a
 * screen reader announces which match is being picked.
 *
 * Saving is optimistic. A pick is a two-byte write to a table nobody else can
 * see yet; making somebody watch a spinner for it would be theatre.
 */

import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '@/api/client'
import type { Club } from '@/api/types'

interface Props {
  fixtureId: number
  home: Club
  away: Club
  homeGoals: number | null
  awayGoals: number | null
  disabled?: boolean
}

const MAX = 9

export function ScorePicker({ fixtureId, home, away, homeGoals, awayGoals, disabled }: Props) {
  const client = useQueryClient()
  const [h, setH] = useState(homeGoals ?? 0)
  const [a, setA] = useState(awayGoals ?? 0)
  const [touched, setTouched] = useState(homeGoals !== null || awayGoals !== null)

  // A refetch that brings a newer pick down should win over local state --
  // otherwise a pick made on a phone is silently reverted by a stale tab.
  useEffect(() => {
    if (homeGoals !== null) setH(homeGoals)
    if (awayGoals !== null) setA(awayGoals)
    if (homeGoals !== null || awayGoals !== null) setTouched(true)
  }, [homeGoals, awayGoals])

  const save = useMutation({
    mutationFn: (next: { home: number; away: number }) =>
      api.put('/api/picks', {
        fixture_id: fixtureId,
        home_goals: next.home,
        away_goals: next.away,
      }),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ['picks'] })
    },
  })

  const commit = (nextH: number, nextA: number) => {
    setH(nextH)
    setA(nextA)
    setTouched(true)
    save.mutate({ home: nextH, away: nextA })
  }

  const step = (side: 'h' | 'a', delta: number) => {
    const nextH = side === 'h' ? Math.min(MAX, Math.max(0, h + delta)) : h
    const nextA = side === 'a' ? Math.min(MAX, Math.max(0, a + delta)) : a
    if (nextH === h && nextA === a) return
    commit(nextH, nextA)
  }

  if (disabled) return null

  return (
    <div className="picker" role="group" aria-label={`Your score for ${home.name} against ${away.name}`}>
      <Stepper
        label={home.short_name}
        value={h}
        onStep={(d) => step('h', d)}
        describedAs={`${home.name} goals`}
      />
      <span className="picker__dash" aria-hidden="true">
        –
      </span>
      <Stepper
        label={away.short_name}
        value={a}
        onStep={(d) => step('a', d)}
        describedAs={`${away.name} goals`}
      />
      <span className="picker__state" aria-live="polite">
        {save.isError ? (
          <span className="picker__error">
            {save.error instanceof ApiError ? save.error.message : 'Not saved'}
          </span>
        ) : touched ? (
          'Picked'
        ) : (
          'Not picked'
        )}
      </span>
    </div>
  )
}

function Stepper({
  label,
  value,
  onStep,
  describedAs,
}: {
  label: string
  value: number
  onStep: (delta: number) => void
  describedAs: string
}) {
  return (
    <span className="stepper">
      <button
        type="button"
        onClick={() => onStep(-1)}
        disabled={value <= 0}
        aria-label={`One fewer ${describedAs}`}
      >
        −
      </button>
      <span className="stepper__value">
        <b>{value}</b>
        <em>{label}</em>
      </span>
      <button
        type="button"
        onClick={() => onStep(1)}
        disabled={value >= MAX}
        aria-label={`One more ${describedAs}`}
      >
        +
      </button>
    </span>
  )
}
