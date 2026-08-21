/**
 * Build a full 1-20 table from scratch.
 *
 * The brief calls this the most important screen on the site at season start,
 * and three of the four people build it on a phone. So:
 *
 * * every action has a keyboard equivalent -- drag is an enhancement, never the
 *   only way to reorder. The move buttons work with a thumb or a tab key.
 * * already-picked clubs stay visible in the chooser, disabled and annotated
 *   with where they sit, rather than disappearing.
 * * no duplicates and no gaps are possible by construction; the server checks
 *   again anyway, because a client-side check is not a constraint.
 * * the draft is kept in localStorage, so a phone backgrounding the tab
 *   half-way through twenty picks does not lose the lot.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '@/api/client'
import { keys, useClubs, useMe, usePredictions } from '@/api/queries'
import { ClubChooser } from '@/components/ClubChooser'
import { Crest } from '@/components/Crest'
import { Empty, TableSkeleton } from '@/components/states'
import { countdownWords } from '@/lib/format'
import type { Club } from '@/api/types'

const SIZE = 20
const DRAFT_KEY = 'pl:draft-table'

type Slots = (string | null)[]

function emptySlots(): Slots {
  return Array.from({ length: SIZE }, () => null)
}

function zoneOf(position: number): { zone: string; label: string } | null {
  if (position <= 4) return { zone: 'ucl', label: 'UCL' }
  if (position >= 18) return { zone: 'rel', label: 'REL' }
  return null
}

/** Draft persistence. A failure here must never break the picker. */
function readDraft(): Slots | null {
  try {
    const raw = window.localStorage.getItem(DRAFT_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length !== SIZE) return null
    return parsed.map((v) => (typeof v === 'string' ? v : null))
  } catch {
    return null
  }
}

function writeDraft(slots: Slots): void {
  try {
    window.localStorage.setItem(DRAFT_KEY, JSON.stringify(slots))
  } catch {
    /* private mode, quota, or storage disabled -- the picker still works */
  }
}

export function PredictionPicker() {
  const { data: me } = useMe()
  const { data: clubList } = useClubs()
  const { data: predictions, isLoading } = usePredictions()
  const client = useQueryClient()

  const [slots, setSlots] = useState<Slots>(emptySlots)
  const [choosingAt, setChoosingAt] = useState<number | null>(null)
  const [dragFrom, setDragFrom] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState<number | null>(null)
  const [saved, setSaved] = useState(false)
  const loadedFor = useRef<string | null>(null)

  const mine = predictions?.predictions.find((p) => p.person === me?.person.key)
  const locked = predictions?.locked ?? false

  // Seed from the filed table if there is one, else from a saved draft.
  useEffect(() => {
    if (!predictions || !me || loadedFor.current === me.person.key) return
    loadedFor.current = me.person.key
    const filed = mine?.table ?? []
    if (filed.length === SIZE) {
      setSlots(filed)
      return
    }
    const draft = readDraft()
    if (draft) setSlots(draft)
  }, [predictions, me, mine])

  useEffect(() => {
    if (slots.some(Boolean)) writeDraft(slots)
  }, [slots])

  const clubs = clubList ?? []
  const byShort = useMemo(
    () => new Map(clubs.map((c) => [c.short_name, c])),
    [clubs],
  )
  const taken = useMemo(() => {
    const map = new Map<string, number>()
    slots.forEach((short, index) => {
      if (short) map.set(short, index + 1)
    })
    return map
  }, [slots])

  const filled = slots.filter(Boolean).length
  const complete = filled === SIZE

  const save = useMutation({
    mutationFn: (table: string[]) =>
      api.put('/api/predictions', {
        table,
        awards: mine?.awards ?? {},
        champions_league: mine?.champions_league ?? {},
      }),
    onSuccess: async () => {
      setSaved(true)
      writeDraft(emptySlots())
      await client.invalidateQueries({ queryKey: keys.predictions })
    },
  })

  function place(index: number, club: Club) {
    setSaved(false)
    setSlots((current) => {
      const next = [...current]
      // A club can only be in one place, so moving it clears the old slot.
      const existing = next.indexOf(club.short_name)
      if (existing !== -1) next[existing] = null
      next[index] = club.short_name
      return next
    })
    setChoosingAt(null)
  }

  function clear(index: number) {
    setSaved(false)
    setSlots((current) => {
      const next = [...current]
      next[index] = null
      return next
    })
  }

  function move(from: number, to: number) {
    if (to < 0 || to >= SIZE || from === to) return
    setSaved(false)
    setSlots((current) => {
      const next = [...current]
      const [lifted] = next.splice(from, 1)
      next.splice(to, 0, lifted ?? null)
      return next
    })
  }

  if (isLoading || !predictions) return <TableSkeleton rows={20} />

  if (locked) {
    return (
      <section className="section">
        <div className="wrap">
          <div className="shead">
            <h2>Your prediction</h2>
          </div>
          <Empty title="Predictions are locked">
            <p>
              The deadline passed when the season kicked off. Every table is
              read-only now and visible to everyone.
            </p>
          </Empty>
        </div>
      </section>
    )
  }

  return (
    <section className="section" style={{ paddingTop: 24 }}>
      <div className="wrap">
        <div className="shead">
          <h2>Your prediction</h2>
        </div>

        <div className="picker__head">
          <div className="wrap picker__bar" style={{ padding: 0 }}>
            <span className="picker__count">
              <b>{filled}</b> of {SIZE} placed
            </span>
            <span className="picker__count" style={{ color: 'var(--ink-3)' }}>
              locks in {countdownWords(predictions.seconds_remaining)}
            </span>
            <span className="picker__actions">
              <button
                type="button"
                className="btn btn--plain"
                onClick={() => {
                  setSlots(emptySlots())
                  setSaved(false)
                }}
                disabled={filled === 0 || save.isPending}
              >
                Clear
              </button>
              <button
                type="button"
                className="btn"
                disabled={!complete || save.isPending}
                onClick={() => save.mutate(slots.filter((s): s is string => Boolean(s)))}
              >
                {save.isPending ? 'Filing…' : mine?.filed ? 'Update' : 'File it'}
              </button>
            </span>
          </div>
        </div>

        <ol className="slots">
          {slots.map((short, index) => {
            const club = short ? byShort.get(short) : undefined
            const zone = zoneOf(index + 1)
            return (
              <li
                key={index}
                className="slot"
                data-zone={zone?.zone}
                data-over={dragOver === index}
                data-dragging={dragFrom === index}
                onDragOver={(e) => {
                  e.preventDefault()
                  setDragOver(index)
                }}
                onDragLeave={() => setDragOver((v) => (v === index ? null : v))}
                onDrop={(e) => {
                  e.preventDefault()
                  if (dragFrom !== null) move(dragFrom, index)
                  setDragFrom(null)
                  setDragOver(null)
                }}
              >
                <span className="slot__pos">{index + 1}</span>
                <span className="slot__zone" data-zone={zone?.zone}>
                  {zone?.label ?? ''}
                </span>

                {club ? (
                  <>
                    <span
                      className="slot__club"
                      draggable
                      onDragStart={() => setDragFrom(index)}
                      onDragEnd={() => {
                        setDragFrom(null)
                        setDragOver(null)
                      }}
                    >
                      <Crest club={club} size={30} />
                      {/* Both names are rendered and CSS picks one, so the
                          choice follows the viewport rather than a JS guess
                          that would be wrong on first paint. */}
                      <b className="slot__long">{club.full_name}</b>
                      <b className="slot__short">{club.name}</b>
                    </span>
                    {/* Drag is an enhancement; these are the real controls. */}
                    <button
                      type="button"
                      className="slot__grip"
                      onClick={() => move(index, index - 1)}
                      disabled={index === 0}
                      aria-label={`Move ${club.full_name} up to ${index}`}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="slot__grip"
                      onClick={() => move(index, index + 1)}
                      disabled={index === SIZE - 1}
                      aria-label={`Move ${club.full_name} down to ${index + 2}`}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className="slot__x"
                      onClick={() => clear(index)}
                      aria-label={`Remove ${club.full_name} from position ${index + 1}`}
                    >
                      ×
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="slot__club slot__empty"
                    style={{ background: 'none', border: 0, cursor: 'pointer', textAlign: 'left' }}
                    onClick={() => setChoosingAt(index)}
                  >
                    Choose a club for {index + 1}
                  </button>
                )}
              </li>
            )
          })}
        </ol>

        {save.isError && (
          <p className="picker__error" role="alert">
            {save.error instanceof ApiError
              ? save.error.message
              : 'Could not file that. Try again.'}
          </p>
        )}
        {saved && (
          <p className="picker__saved" role="status">
            Filed. You can keep editing until the lock.
          </p>
        )}
        {!complete && (
          <p className="tnote">
            All {SIZE} positions must be filled before you can file. No duplicates,
            no gaps — the server checks again when you submit.
          </p>
        )}

        {choosingAt !== null && (
          <ClubChooser
            clubs={clubs}
            taken={taken}
            position={choosingAt + 1}
            onPick={(club) => place(choosingAt, club)}
            onClose={() => setChoosingAt(null)}
          />
        )}
      </div>
    </section>
  )
}
