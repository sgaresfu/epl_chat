import { useState, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/api/client'
import { keys, useBets, useMe, usePoll, useQuotes, useTimeline } from '@/api/queries'
import { Empty, TableSkeleton } from '@/components/states'
import { plural } from '@/lib/plural'
import type { Poll as PollType } from '@/api/types'

const PEOPLE = ['coyg', 'aure', 'twzt', 'bulba'] as const

function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

function Quotes() {
  const { data, isLoading } = useQuotes()
  const client = useQueryClient()
  const [body, setBody] = useState('')

  const add = useMutation({
    mutationFn: (text: string) => api.post('/api/chat/quotes', { body: text }),
    onSuccess: async () => {
      setBody('')
      await client.invalidateQueries({ queryKey: keys.quotes })
      await client.invalidateQueries({ queryKey: keys.timeline })
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    if (body.trim()) add.mutate(body.trim())
  }

  return (
    <>
      <form className="composer" onSubmit={submit}>
        <label className="sr-only" htmlFor="quote">
          Add a quote
        </label>
        <input
          id="quote"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Say something worth remembering"
          maxLength={500}
        />
        <button className="btn" type="submit" disabled={!body.trim() || add.isPending}>
          {add.isPending ? 'Saving…' : 'Add'}
        </button>
      </form>

      {isLoading ? (
        <TableSkeleton rows={3} />
      ) : !data || data.length === 0 ? (
        <Empty title="Nothing said yet">
          <p>
            Quotes are kept for the season and resurfaced later. Pin one to a club or a
            match and it comes back when it is funniest.
          </p>
        </Empty>
      ) : (
        data.slice(0, 8).map((quote) => (
          <div className="quote-card" key={quote.id}>
            <p className="quote-card__body">&ldquo;{quote.body}&rdquo;</p>
            <p className="quote-card__meta">
              <span className="quote-card__who">{quote.person.toUpperCase()}</span>
              <span>{ago(quote.created_at)}</span>
              {quote.subject_id && <span className="tag">{quote.subject_id}</span>}
            </p>
          </div>
        ))
      )}
    </>
  )
}

function PollPanel({ poll, votable }: { poll: PollType; votable: boolean }) {
  const client = useQueryClient()
  const vote = useMutation({
    mutationFn: (choice: string) => api.post('/api/chat/poll', { poll_id: poll.id, choice }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.poll }),
  })

  return (
    <div style={{ marginBottom: 32 }}>
      <h3 style={{ fontSize: 19, fontWeight: 600, letterSpacing: '-0.02em', marginBottom: 14 }}>
        {poll.question}
      </h3>
      {poll.options.map((option) => {
        const share = poll.total_votes ? (option.votes / poll.total_votes) * 100 : 0
        return (
          <button
            key={option.choice}
            className="poll__option"
            type="button"
            data-mine={poll.my_vote === option.choice}
            disabled={!votable || vote.isPending}
            onClick={() => vote.mutate(option.choice)}
          >
            <span className="poll__fill" style={{ width: `${share}%` }} />
            <span className="poll__label">
              <span>{option.choice}</span>
              {option.voters.length > 0 && (
                <span className="poll__voters">
                  {option.voters.map((v) => v.toUpperCase()).join(', ')}
                </span>
              )}
              <span className="poll__count">{option.votes}</span>
            </span>
          </button>
        )
      })}
      <p className="tnote">
        {poll.total_votes} of 4 voted.{' '}
        {votable ? 'You can change your mind until it closes.' : 'Closed.'}
      </p>
    </div>
  )
}

function Polls() {
  const { data, isLoading } = usePoll()
  if (isLoading) return <TableSkeleton rows={4} />
  if (!data || (!data.current && data.archive.length === 0)) {
    return (
      <Empty title="No poll running">
        <p>{data?.empty_message}</p>
      </Empty>
    )
  }
  return (
    <>
      {data.current && <PollPanel poll={data.current} votable />}
      {data.archive.length > 0 && (
        <>
          <h3 style={{ fontSize: 13, textTransform: 'uppercase', color: 'var(--ink-3)', margin: '32px 0 16px' }}>
            Archive
          </h3>
          {data.archive.map((p) => (
            <PollPanel key={p.id} poll={p} votable={false} />
          ))}
        </>
      )}
    </>
  )
}

function BetsPanel() {
  const { data, isLoading } = useBets()
  const { data: me } = useMe()
  const client = useQueryClient()
  const [opponent, setOpponent] = useState<string>('aure')
  const [terms, setTerms] = useState('')

  const propose = useMutation({
    mutationFn: () => api.post('/api/chat/bets', { opponent, terms: terms.trim() }),
    onSuccess: async () => {
      setTerms('')
      await client.invalidateQueries({ queryKey: keys.bets })
      await client.invalidateQueries({ queryKey: keys.timeline })
    },
  })

  const settle = useMutation({
    mutationFn: (v: { bet_id: number; winner: string }) => api.put('/api/chat/bets', v),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: keys.bets })
      await client.invalidateQueries({ queryKey: keys.timeline })
    },
  })

  if (isLoading || !data) return <TableSkeleton rows={3} />

  const others = PEOPLE.filter((p) => p !== me?.person.key)

  return (
    <>
      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault()
          if (terms.trim()) propose.mutate()
        }}
      >
        <label className="sr-only" htmlFor="opp">
          Opponent
        </label>
        <select id="opp" value={opponent} onChange={(e) => setOpponent(e.target.value)}>
          {others.map((p) => (
            <option key={p} value={p}>
              {p.toUpperCase()}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="terms">
          Terms
        </label>
        <input
          id="terms"
          value={terms}
          onChange={(e) => setTerms(e.target.value)}
          placeholder="What are you betting on?"
          maxLength={500}
        />
        <button className="btn" type="submit" disabled={!terms.trim() || propose.isPending}>
          Propose
        </button>
      </form>

      {data.bets.length === 0 ? (
        <Empty title="No bets yet">
          <p>{data.empty_message}</p>
        </Empty>
      ) : (
        data.bets.slice(0, 6).map((bet) => {
          const mine = me?.person.key === bet.proposer || me?.person.key === bet.opponent
          return (
            <div className="bet" key={bet.id}>
              <div className="bet__head">
                <span className="bet__who">
                  {bet.proposer.toUpperCase()} v {bet.opponent.toUpperCase()}
                </span>
                <span style={{ fontSize: 13, color: 'var(--ink-3)' }}>{ago(bet.created_at)}</span>
                {bet.settled && (
                  <span className="tag" style={{ color: 'var(--green-ink)', borderColor: 'var(--green-line)' }}>
                    {bet.winner?.toUpperCase()} won
                  </span>
                )}
              </div>
              <p className="bet__terms">{bet.terms}</p>
              {!bet.settled && mine && (
                <div className="acts">
                  {[bet.proposer, bet.opponent].map((who) => (
                    <button
                      key={who}
                      className="chip"
                      type="button"
                      disabled={settle.isPending}
                      onClick={() => settle.mutate({ bet_id: bet.id, winner: who })}
                    >
                      {who.toUpperCase()} won
                    </button>
                  ))}
                </div>
              )}
            </div>
          )
        })
      )}
    </>
  )
}

function Feed() {
  const { data, isLoading } = useTimeline()
  if (isLoading) return <TableSkeleton rows={5} />
  if (!data || data.entries.length === 0) {
    return (
      <Empty title="Nothing yet">
        <p>{data?.empty_message}</p>
      </Empty>
    )
  }
  return (
    <div className="feed">
      {data.entries.slice(0, 12).map((entry, index) => (
        <div className="feed__row" key={`${entry.kind}-${entry.at}-${index}`}>
          <span className="feed__kind">{entry.kind.replace('-', ' ')}</span>
          <span className="feed__body">
            <span className="feed__title">
              {entry.person ? `${entry.person.toUpperCase()} · ` : ''}
              {entry.title}
            </span>
            {entry.detail && <span className="feed__detail">{entry.detail}</span>}
          </span>
          <span className="feed__when">{ago(entry.at)}</span>
        </div>
      ))}
    </div>
  )
}

export function Chat() {
  const { data: bets } = useBets()
  const { data: poll } = usePoll()
  const { data: quotes } = useQuotes()
  const { data: timeline } = useTimeline()

  const board = Object.entries(bets?.scoreboard ?? {})
  const leader = Math.max(0, ...board.map(([, n]) => n))

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>The group</h2>
          <span className="shead__link" style={{ color: 'var(--ink-3)' }}>
            {plural(quotes?.length ?? 0, 'quote')} ·{' '}
            {plural(bets?.bets.length ?? 0, 'bet')} ·{' '}
            {plural(timeline?.entries.length ?? 0, 'entry', 'entries')}
          </span>
        </div>

        <div className="hub">
          <div>
            <div className="hub__panel">
              <p className="hub__title">Quotes</p>
              <Quotes />
            </div>

            <div className="hub__panel">
              <p className="hub__title">
                Timeline
                <span>everything, newest first</span>
              </p>
              <Feed />
            </div>
          </div>

          <aside>
            <div className="hub__panel" style={{ marginTop: 0 }}>
              <p className="hub__title">
                This week&rsquo;s poll
                {poll?.current && <span>{poll.current.total_votes} of 4 voted</span>}
              </p>
              <Polls />
            </div>

            <div className="hub__panel">
              <p className="hub__title">
                Settled bets
                <span>no money, just a record</span>
              </p>
              {board.length > 0 && (
                <div className="ledger">
                  {board
                    .sort((a, b) => b[1] - a[1])
                    .map(([person, wins]) => (
                      <div
                        className="ledger__cell"
                        key={person}
                        data-lead={wins > 0 && wins === leader}
                      >
                        <p className="ledger__who">{person.toUpperCase()}</p>
                        <p className="ledger__wins">{wins}</p>
                      </div>
                    ))}
                </div>
              )}
              <BetsPanel />
            </div>
          </aside>
        </div>
      </div>
    </section>
  )
}
