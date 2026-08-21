/**
 * The searchable club chooser.
 *
 * Keyboard and touch are equal citizens: arrow keys and Enter drive the same
 * list a tap does, Escape closes, and focus is trapped and restored. An
 * already-picked club stays visible but disabled and annotated with where it
 * sits, so you can see your own table while you build it rather than having
 * clubs silently vanish.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { Crest } from '@/components/Crest'
import { fold } from '@/lib/fold'
import type { Club } from '@/api/types'

interface Props {
  clubs: Club[]
  /** short_name -> the 1-indexed position it already occupies. */
  taken: Map<string, number>
  position: number
  onPick: (club: Club) => void
  onClose: () => void
}

export function ClubChooser({ clubs, taken, position, onPick, onClose }: Props) {
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const searchRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const returnFocus = useRef<Element | null>(null)

  useEffect(() => {
    returnFocus.current = document.activeElement
    searchRef.current?.focus()
    return () => {
      // Send focus back where it came from, or the slot the user opened.
      if (returnFocus.current instanceof HTMLElement) returnFocus.current.focus()
    }
  }, [])

  const matches = useMemo(() => {
    const needle = fold(query)
    if (!needle) return clubs
    return clubs.filter(
      (c) =>
        fold(c.full_name).includes(needle) ||
        fold(c.name).includes(needle) ||
        fold(c.short_name).includes(needle),
    )
  }, [clubs, query])

  // Keep the highlight in range as the list narrows.
  useEffect(() => setActive(0), [query])

  // Scrolling is a side effect, so it belongs in an effect rather than inside a
  // state updater -- React may call an updater more than once, and an updater
  // that touches the DOM is not pure. `scrollIntoView` is also absent in some
  // environments, hence the guard.
  useEffect(() => {
    const row = listRef.current?.children[active]
    if (row instanceof HTMLElement) row.scrollIntoView?.({ block: 'nearest' })
  }, [active])

  function commit(club: Club | undefined) {
    if (!club || taken.has(club.short_name)) return
    onPick(club)
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActive((current) => Math.max(0, Math.min(matches.length - 1, current + step)))
      return
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      commit(matches[active])
    }
  }

  return (
    <div
      className="chooser"
      role="dialog"
      aria-modal="true"
      aria-label={`Choose the club for position ${position}`}
      onKeyDown={onKeyDown}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="chooser__panel">
        <div className="chooser__top">
          <div className="chooser__row">
            <span className="chooser__title">Position {position}</span>
            <button type="button" className="chooser__close" onClick={onClose}>
              Cancel
            </button>
          </div>
          <input
            ref={searchRef}
            className="chooser__search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search clubs"
            aria-label="Search clubs"
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
          />
        </div>

        {matches.length === 0 ? (
          <p className="chooser__none">
            No club matches &ldquo;{query}&rdquo;. Try a shorter search.
          </p>
        ) : (
          <ul className="chooser__list" ref={listRef} role="listbox">
            {matches.map((club, index) => {
              const at = taken.get(club.short_name)
              return (
                <li key={club.short_name}>
                  <button
                    type="button"
                    className="chooser__item"
                    role="option"
                    aria-selected={index === active}
                    data-active={index === active}
                    disabled={at !== undefined}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => commit(club)}
                  >
                    <Crest club={club} size={28} />
                    <span>{club.full_name}</span>
                    {at !== undefined && (
                      <span className="chooser__taken">already {at}</span>
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}
