/**
 * The news page: a lead story with its picture, a dense list beneath, and a
 * video rail alongside.
 *
 * A feed of blue links does not read as current. The outlets publish their own
 * syndication thumbnails in RSS — which is what those are for — so the lead
 * carries one at full width and the rest carry one at list size.
 */

import { useMemo, useState } from 'react'
import { useNews } from '@/api/queries'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'
import type { NewsItem } from '@/api/types'

function ago(iso: string | null): string {
  if (!iso) return ''
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

function Lead({ item }: { item: NewsItem }) {
  return (
    <a className="lead-story" href={item.url} target="_blank" rel="noreferrer noopener">
      {item.image && (
        <div className="lead-story__art">
          <img src={item.image} alt="" loading="eager" />
        </div>
      )}
      <div className="lead-story__body">
        <p className="story__meta" style={{ marginTop: 0, marginBottom: 8 }}>
          <span className="story__source">{item.source}</span>
          <span>·</span>
          <span>{ago(item.published)}</span>
        </p>
        <h3>{item.title}</h3>
        {item.summary && <p>{item.summary}</p>}
      </div>
    </a>
  )
}

function Story({ item }: { item: NewsItem }) {
  return (
    <a className="story" href={item.url} target="_blank" rel="noreferrer noopener">
      {item.image && (
        <div className="story__art">
          <img src={item.image} alt="" loading="lazy" />
        </div>
      )}
      <div className="story__body">
        <p className="story__title">{item.title}</p>
        <p className="story__meta">
          <span className="story__source">{item.source}</span>
          <span>·</span>
          <span>{ago(item.published)}</span>
        </p>
      </div>
    </a>
  )
}

function Video({ item }: { item: NewsItem }) {
  return (
    <a className="video" href={item.url} target="_blank" rel="noreferrer noopener">
      {item.image && (
        <div className="video__art">
          <img src={item.image} alt="" loading="lazy" />
        </div>
      )}
      <p className="video__title">{item.title}</p>
      <p className="video__channel">
        {item.source} · {ago(item.published)}
      </p>
    </a>
  )
}

export function News() {
  const { data, isLoading } = useNews()
  const [source, setSource] = useState<string>('all')

  const sources = useMemo(() => {
    const seen = new Set((data?.sky ?? []).map((i) => i.source))
    return ['all', ...Array.from(seen)]
  }, [data])

  const shown = useMemo(() => {
    const items = data?.sky ?? []
    return source === 'all' ? items : items.filter((i) => i.source === source)
  }, [data, source])

  if (isLoading) return <TableSkeleton rows={6} />

  const [lead, ...rest] = shown

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>News</h2>
          <span className="shead__link" style={{ color: 'var(--ink-3)' }}>
            {(data?.sources ?? []).join(' · ')}
          </span>
        </div>

        {sources.length > 2 && (
          <div className="source-filter">
            {sources.map((s) => (
              <button
                key={s}
                type="button"
                className="chip"
                aria-pressed={source === s}
                onClick={() => setSource(s)}
              >
                {s === 'all' ? 'All' : s}
              </button>
            ))}
          </div>
        )}

        {shown.length === 0 ? (
          <Empty title="No headlines yet">
            <p>{data?.empty_message ?? 'They appear once the poller has read the feeds.'}</p>
          </Empty>
        ) : (
          <div className="news-layout">
            <div>
              {lead && <Lead item={lead} />}
              {rest.map((item) => (
                <Story key={item.url} item={item} />
              ))}
              {data && <StaleNote freshness={data.freshness} label="Headlines" />}
            </div>

            <aside>
              {(data?.youtube.length ?? 0) > 0 ? (
                <>
                  <p className="rail__head">Latest video</p>
                  {data?.youtube.slice(0, 6).map((item) => (
                    <Video key={item.url} item={item} />
                  ))}
                </>
              ) : (
                <>
                  <p className="rail__head">Video</p>
                  <p className="tnote" style={{ marginTop: 0 }}>
                    {data?.youtube_message}
                  </p>
                </>
              )}
              <p className="tnote" style={{ marginTop: 26 }}>
                {data?.athletic_message}
              </p>
            </aside>
          </div>
        )}
      </div>
    </section>
  )
}
