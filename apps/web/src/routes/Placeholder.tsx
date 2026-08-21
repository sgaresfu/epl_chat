/**
 * Routes whose data sources are not wired yet.
 *
 * These ship the empty state deliberately rather than 404ing: the brief's rule
 * is that a panel with no data explains what will appear and when. Each one
 * names its own blocker honestly instead of pretending to be finished.
 */

import { Empty } from '@/components/states'

interface Props {
  title: string
  blurb: string
}

export function Placeholder({ title, blurb }: Props) {
  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>{title}</h2>
        </div>
        <Empty title="Not wired up yet">
          <p>{blurb}</p>
        </Empty>
      </div>
    </section>
  )
}
