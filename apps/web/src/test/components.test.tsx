import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Crest } from '@/components/Crest'
import { FourCities } from '@/components/FourCities'
import { Empty, StaleNote, describeAge } from '@/components/states'
import type { Club, Freshness, LocalTime } from '@/api/types'

const ARSENAL: Club = {
  short_name: 'ARS', name: 'Arsenal', full_name: 'Arsenal',
  primary: '#EF0107', on_primary: '#FFFFFF', fpl_id: 1,
}
const COVENTRY: Club = {
  short_name: 'COV', name: 'Coventry', full_name: 'Coventry City',
  primary: '#7BC5EC', on_primary: '#003087', fpl_id: 7,
}

describe('Crest', () => {
  it('renders the three-letter monogram', () => {
    const { container } = render(<Crest club={ARSENAL} />)
    expect(container.textContent).toBe('ARS')
  })

  it('uses the club colour as the disc', () => {
    const { container } = render(<Crest club={ARSENAL} />)
    const el = container.firstElementChild as HTMLElement
    expect(el.style.background).toBe('rgb(239, 1, 7)')
  })

  it('uses dark text on a light club colour', () => {
    // Coventry's sky blue cannot carry white text at AA contrast.
    const { container } = render(<Crest club={COVENTRY} />)
    const el = container.firstElementChild as HTMLElement
    expect(el.style.color).toBe('rgb(0, 48, 135)')
  })

  it('is hidden from assistive tech, since the club name sits beside it', () => {
    const { container } = render(<Crest club={ARSENAL} />)
    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true')
  })
})

function slot(over: Partial<LocalTime> = {}): LocalTime {
  return {
    place: 'coyg', person: 'COYG', city: 'Lviv', timezone: 'Europe/Kyiv',
    iso: '2026-08-21T22:00:00+03:00', time: '22:00', weekday: 'Fri', day: '21 Aug',
    offset: 'UTC+3', abbreviation: 'EEST', is_night: false, day_shift: 0,
    broadcaster: 'Setanta Sports', broadcaster_url: 'https://setantasports.com/',
    verified_on: '2026-08-21', ...over,
  }
}

describe('FourCities', () => {
  const times = [
    slot(),
    slot({ place: 'aure', city: 'Michigan', time: '15:00', broadcaster: 'Peacock' }),
    slot({ place: 'twzt', city: 'Alberta', time: '13:00', broadcaster: 'Fubo' }),
    slot({ place: 'bulba', city: 'Alaska', time: '11:00', broadcaster: 'Peacock' }),
  ]

  it('shows all four cities with their own kick-off time', () => {
    render(<FourCities times={times} me="coyg" />)
    for (const t of ['22:00', '15:00', '13:00', '11:00']) {
      expect(screen.getByText(t)).toBeInTheDocument()
    }
  })

  it('names the broadcaster for each city', () => {
    render(<FourCities times={times} me="coyg" />)
    expect(screen.getByText('Setanta Sports')).toBeInTheDocument()
    expect(screen.getByText('Fubo')).toBeInTheDocument()
    expect(screen.getAllByText('Peacock')).toHaveLength(2)
  })

  it('marks the logged-in person’s own city', () => {
    const { container } = render(<FourCities times={times} me="bulba" />)
    const mine = container.querySelector('[data-mine="true"]')
    expect(mine?.textContent).toContain('Alaska')
    expect(mine?.textContent).toContain('you')
  })

  it('flags a kick-off that lands on the next local day', () => {
    render(<FourCities times={[slot({ day_shift: 1, time: '01:00' })]} me="coyg" />)
    expect(screen.getByText('+1')).toBeInTheDocument()
  })

  it('flags a kick-off that lands on the previous local day', () => {
    render(<FourCities times={[slot({ place: 'bulba', day_shift: -1 })]} me="coyg" />)
    expect(screen.getByText('−1')).toBeInTheDocument()
  })

  it('says the listing is unconfirmed rather than inventing one', () => {
    render(<FourCities times={[slot({ broadcaster: null, broadcaster_url: null })]} me="coyg" />)
    expect(screen.getByText('Listing to confirm')).toBeInTheDocument()
  })
})

describe('empty and stale states', () => {
  it('an empty panel says what will appear, not "no data"', () => {
    render(
      <Empty title="Nobody has played yet">
        <p>All 20 clubs start on zero points.</p>
      </Empty>,
    )
    expect(screen.getByText('Nobody has played yet')).toBeInTheDocument()
    expect(screen.queryByText(/no data/i)).not.toBeInTheDocument()
  })

  it('describes a cache age in words a person would use', () => {
    expect(describeAge(30)).toBe('updated just now')
    expect(describeAge(60 * 47)).toBe('updated 47 minutes ago')
    expect(describeAge(3600 * 3)).toBe('updated 3 hours ago')
  })

  it('says nothing at all when the data is fresh', () => {
    const fresh: Freshness = { source: 'fpl', age_seconds: 4, stale: false, available: true, reason: null }
    const { container } = render(<StaleNote freshness={fresh} label="Odds" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the age when the data is stale rather than hiding it', () => {
    const stale: Freshness = { source: 'fpl', age_seconds: 2820, stale: true, available: true, reason: null }
    render(<StaleNote freshness={stale} label="Odds" />)
    expect(screen.getByText('Odds updated 47 minutes ago.')).toBeInTheDocument()
  })

  it('explains an absent payload instead of showing a blank panel', () => {
    const missing: Freshness = {
      source: 'none', age_seconds: 0, stale: true, available: false,
      reason: 'Waiting for the first update from the poller.',
    }
    render(<StaleNote freshness={missing} label="Odds" />)
    expect(screen.getByText(/Waiting for the first update/)).toBeInTheDocument()
  })
})

describe('live score layout', () => {
  it('puts the minute on its own line, not welded to the score', () => {
    // The deployed board read "3-090' - live" because .score small had no
    // display:block, unlike .countdown small.
    const css = readFileSync(resolve(process.cwd(), 'src/styles/app.css'), 'utf8')
    const block = css.slice(css.indexOf('.score small'))
    expect(block.slice(0, 200)).toContain('display: block')
  })
})
