/**
 * 26/27 as the first season (brief §6, "/archive").
 *
 * There is nothing to look back on yet -- this reads as "the season so far,"
 * not a finished record. The season selector has exactly one option today;
 * a second season slots in by adding an option here, not by rewriting the
 * page.
 */

import { Link } from 'react-router-dom'
import { useMe } from '@/api/queries'
import { Standings } from '@/routes/Predictions'
import { TablePreview } from '@/routes/Home'

export function Archive() {
  const { data: me } = useMe()
  const season = me?.season ?? '2026-27'

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Archive</h2>
          <span className="seg" role="tablist" aria-label="Season">
            <button type="button" role="tab" aria-selected="true">
              {season}
            </button>
          </span>
        </div>
        <p className="lead" style={{ marginBottom: 32 }}>
          {season} is the first season of the Prediction League. This page is built to
          hold more than one — a season selector is all a future year needs to slot in.
        </p>

        <div className="shead" style={{ marginTop: 0 }}>
          <h2>Standings</h2>
          <Link className="shead__link" to="/predictions">
            Full predictions
          </Link>
        </div>
        <Standings />

        <hr className="rule" style={{ margin: '40px 0' }} />

        <div className="shead">
          <h2>Table</h2>
          <Link className="shead__link" to="/table">
            Full table
          </Link>
        </div>
        <TablePreview />
      </div>
    </section>
  )
}
