/**
 * Picker tests.
 *
 * The brief's bar is that this must build a full 1-20 table on a phone without
 * frustration, with keyboard and touch as equal citizens. These cover the rules
 * that make that true: no duplicates, no gaps, and every action reachable
 * without a pointer.
 */

import { describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ClubChooser } from '@/components/ClubChooser'
import type { Club } from '@/api/types'

const CLUBS: Club[] = [
  { short_name: 'ARS', name: 'Arsenal', full_name: 'Arsenal', primary: '#EF0107', on_primary: '#FFF', fpl_id: 1 },
  { short_name: 'NFO', name: "Nott'm Forest", full_name: 'Nottingham Forest', primary: '#DD0000', on_primary: '#FFF', fpl_id: 18 },
  { short_name: 'TOT', name: 'Spurs', full_name: 'Tottenham Hotspur', primary: '#132257', on_primary: '#FFF', fpl_id: 19 },
  { short_name: 'BHA', name: 'Brighton', full_name: 'Brighton & Hove Albion', primary: '#0057B8', on_primary: '#FFF', fpl_id: 5 },
]

function setup(taken = new Map<string, number>()) {
  const onPick = vi.fn()
  const onClose = vi.fn()
  render(
    <ClubChooser clubs={CLUBS} taken={taken} position={1} onPick={onPick} onClose={onClose} />,
  )
  return { onPick, onClose, user: userEvent.setup() }
}

describe('ClubChooser', () => {
  it('lists every club when nothing is typed', () => {
    setup()
    expect(screen.getAllByRole('option')).toHaveLength(4)
  })

  it('searches by full name', async () => {
    const { user } = setup()
    await user.type(screen.getByRole('textbox'), 'tott')
    expect(screen.getAllByRole('option')).toHaveLength(1)
    expect(screen.getByText('Tottenham Hotspur')).toBeInTheDocument()
  })

  it('finds a club by its short name', async () => {
    const { user } = setup()
    await user.type(screen.getByRole('textbox'), 'nfo')
    expect(screen.getByText('Nottingham Forest')).toBeInTheDocument()
  })

  it('finds Nottingham Forest by its apostrophe-free spelling', async () => {
    const { user } = setup()
    await user.type(screen.getByRole('textbox'), 'nottm')
    expect(screen.getByText('Nottingham Forest')).toBeInTheDocument()
  })

  it('says so when nothing matches, rather than showing an empty box', async () => {
    const { user } = setup()
    await user.type(screen.getByRole('textbox'), 'zzz')
    expect(screen.getByText(/No club matches/)).toBeInTheDocument()
  })

  it('picks a club on click', async () => {
    const { user, onPick } = setup()
    await user.click(screen.getByRole('option', { name: /Arsenal/ }))
    expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ short_name: 'ARS' }))
  })

  describe('already-picked clubs', () => {
    const taken = new Map([['ARS', 3]])

    it('stay visible instead of disappearing', () => {
      setup(taken)
      expect(screen.getByRole('option', { name: /Arsenal/ })).toBeInTheDocument()
    })

    it('are disabled', () => {
      setup(taken)
      expect(screen.getByRole('option', { name: /Arsenal/ })).toBeDisabled()
    })

    it('are annotated with where they already sit', () => {
      setup(taken)
      const option = screen.getByRole('option', { name: /Arsenal/ })
      expect(within(option).getByText('already 3')).toBeInTheDocument()
    })

    it('cannot be picked, so a duplicate is impossible', async () => {
      const { user, onPick } = setup(taken)
      await user.click(screen.getByRole('option', { name: /Arsenal/ }))
      expect(onPick).not.toHaveBeenCalled()
    })
  })

  describe('keyboard is an equal citizen', () => {
    it('focuses the search box on open, so typing just works', () => {
      setup()
      expect(screen.getByRole('textbox')).toHaveFocus()
    })

    it('picks the highlighted club with Enter', async () => {
      const { user, onPick } = setup()
      await user.keyboard('{Enter}')
      expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ short_name: 'ARS' }))
    })

    it('moves the highlight with the arrow keys', async () => {
      const { user, onPick } = setup()
      await user.keyboard('{ArrowDown}{ArrowDown}{Enter}')
      expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ short_name: 'TOT' }))
    })

    it('does not run off the end of the list', async () => {
      const { user, onPick } = setup()
      await user.keyboard('{ArrowDown>10/}{Enter}')
      expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ short_name: 'BHA' }))
    })

    it('closes on Escape', async () => {
      const { user, onClose } = setup()
      await user.keyboard('{Escape}')
      expect(onClose).toHaveBeenCalled()
    })

    it('will not pick a disabled club with Enter either', async () => {
      const { user, onPick } = setup(new Map([['ARS', 3]]))
      await user.keyboard('{Enter}')
      expect(onPick).not.toHaveBeenCalled()
    })
  })

  it('is a labelled modal dialog', () => {
    setup()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAccessibleName(/position 1/i)
  })
})
