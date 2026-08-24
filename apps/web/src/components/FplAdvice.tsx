/**
 * Projections, captaincy and transfer advice for all four squads.
 *
 * Two rules run through this. Every recommendation shows its reasoning,
 * because advice you cannot argue with is advice you cannot trust. And every
 * projection shows what it rests on — a number built mostly from the league's
 * own expectation is labelled as such, so nobody reads an August estimate as
 * though it carried a season of evidence behind it.
 *
 * "Worst managed" deliberately measures decisions, not luck. A low score can
 * be a bad afternoon; points left on the bench and the wrong armband are
 * choices, and those are the only two things worth calling somebody out for.
 */

import { useState } from 'react'
import { useFplAdvice, useMe } from '@/api/queries'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'
import type { Forecast, ManagerAdvice, ManagerReport, TransferIdea } from '@/api/types'

const BASIS_LABEL: Record<string, string> = {
  observed: 'from their own record',
  blended: 'part record, part league expectation',
  prior: "the league's own expectation",
  thin: 'too little to judge',
}

function Basis({ player }: { player: Forecast }) {
  if (player.basis === 'observed') return null
  return (
    <span
      className="basis"
      title={`${BASIS_LABEL[player.basis] ?? player.basis} — ${player.appearances} full match${player.appearances === 1 ? '' : 'es'} played`}
    >
      est.
    </span>
  )
}

/** Reasons arrive lowercase so they can be joined mid-sentence; when one
 *  starts a sentence it needs a capital. */
function sentence(text: string): string {
  return text ? text[0]!.toUpperCase() + text.slice(1) : text
}

function CaptainCard({ manager }: { manager: ManagerAdvice }) {
  const best = manager.captains[0]
  if (!best) return null
  const changing = manager.captain_now !== best.player.name

  return (
    <div className="advice__block">
      <p className="advice__label">Armband</p>
      <p className="advice__lead">
        {best.player.name}
        <Basis player={best.player} />
        <span className="advice__num">{best.doubled}</span>
      </p>
      <p className="advice__why">
        {changing && manager.captain_now
          ? `Currently ${manager.captain_now}. `
          : 'Already captained. '}
        {best.player.reasons.length > 0
          ? `${sentence(best.player.reasons.join('; '))}.`
          : `Projected ${best.player.expected_points} before doubling.`}
      </p>
      {manager.captains.length > 1 && (
        <p className="advice__alts">
          Then{' '}
          {manager.captains
            .slice(1)
            .map((c) => `${c.player.name} (${c.doubled})`)
            .join(', ')}
        </p>
      )}
    </div>
  )
}

function Transfer({ idea }: { idea: TransferIdea }) {
  return (
    <li className="swap">
      <p className="swap__line">
        <span className="swap__out">
          {idea.out_player.name}
          <em>£{idea.out_player.price}m</em>
        </span>
        <span className="swap__arrow" aria-hidden="true">
          →
        </span>
        <span className="swap__in">
          {idea.in_player.name}
          <Basis player={idea.in_player} />
          <em>£{idea.in_player.price}m</em>
        </span>
        <span className="swap__gain">+{idea.gain}</span>
      </p>
      <p className="swap__why">{sentence(idea.reasoning.join(' · '))}</p>
    </li>
  )
}

function ManagerPanel({ manager, report, worst }: {
  manager: ManagerAdvice
  report: ManagerReport | undefined
  worst: boolean
}) {
  return (
    <div className="advice" data-worst={worst}>
      <div className="advice__head">
        <span className="advice__who">
          {manager.person.toUpperCase()}
          {worst && <span className="tag tag--warn">most left on the table</span>}
        </span>
        <span className="advice__proj" title="Projected points for the coming round">
          {manager.projected_points}
          <small>proj</small>
        </span>
      </div>

      {report && (report.bench_wasted > 0 || report.captain_cost > 0) && (
        <p className="advice__regret">
          {report.captain_cost > 0 && (
            <span>
              {report.best_captain} over {report.captain} would have added {report.captain_cost}.
            </span>
          )}
          {report.bench_wasted > 0 && <span>{report.bench_wasted} left on the bench.</span>}
        </p>
      )}

      <CaptainCard manager={manager} />

      <div className="advice__block">
        <p className="advice__label">
          Transfers <span className="advice__bank">£{manager.bank}m in the bank</span>
        </p>
        {manager.transfers.length === 0 ? (
          <p className="advice__why">Nothing worth doing — no affordable upgrade projects higher.</p>
        ) : (
          <ul className="swaps">
            {manager.transfers.map((idea) => (
              <Transfer key={`${idea.out_player.element}-${idea.in_player.element}`} idea={idea} />
            ))}
          </ul>
        )}
      </div>

      {manager.note && <p className="advice__note">{manager.note}</p>}
    </div>
  )
}

export function FplAdvicePanel() {
  const { data, isLoading } = useFplAdvice()
  const { data: me } = useMe()
  const [mineOnly, setMineOnly] = useState(false)

  if (isLoading) return <TableSkeleton rows={6} />
  if (!data || data.managers.length === 0) {
    return (
      <Empty title="No advice yet">
        <p>{data?.empty_message ?? 'Advice appears once the squads have loaded.'}</p>
      </Empty>
    )
  }

  const reports = new Map(data.reports.map((r) => [r.person, r]))
  const shown = mineOnly ? data.managers.filter((m) => m.person === me?.person.key) : data.managers

  return (
    <>
      <div className="shead" style={{ marginTop: 4 }}>
        <h2 style={{ fontSize: 21 }}>Gameweek {data.gameweek}</h2>
        <span className="source-filter" style={{ marginLeft: 'auto' }}>
          <button
            type="button"
            className="chip"
            aria-pressed={!mineOnly}
            onClick={() => setMineOnly(false)}
          >
            All four
          </button>
          <button
            type="button"
            className="chip"
            aria-pressed={mineOnly}
            onClick={() => setMineOnly(true)}
          >
            Just mine
          </button>
        </span>
      </div>

      {data.worst && !mineOnly && (
        <p className="tnote" style={{ marginBottom: 16 }}>
          <b style={{ color: 'var(--ink)' }}>{data.worst.toUpperCase()}</b> left the most on the
          table this round — {data.worst_reason} Measured on decisions, not on the score.
        </p>
      )}

      <div className="advices stagger">
        {shown.map((manager) => (
          <ManagerPanel
            key={manager.person}
            manager={manager}
            report={reports.get(manager.person)}
            worst={manager.person === data.worst && !mineOnly}
          />
        ))}
      </div>

      <p className="tnote" style={{ marginTop: 22 }}>{data.method}</p>
      <StaleNote freshness={data.freshness} label="Squad data" />
    </>
  )
}
