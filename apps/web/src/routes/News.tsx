import { useNews } from '@/api/queries'
import { Empty, StaleNote, TableSkeleton } from '@/components/states'
import type { NewsItem } from '@/api/types'

function when(iso: string | null): string {
  if (!iso) return ''
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000)
  if (minutes < 60) return `${Math.max(1, minutes)}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

function Story({ item }: { item: NewsItem }) {
  return (
    <a className="fxr" href={item.url} target="_blank" rel="noreferrer noopener" style={{ display: 'block' }}>
      <div className="fxr__head">
        <span style={{ fontSize: 17, fontWeight: 500, letterSpacing: '-0.015em', flex: 1 }}>
          {item.title}
        </span>
        <span className="fxr__ko">{when(item.published)}</span>
      </div>
      {item.summary && <p className="tnote" style={{ marginTop: 8 }}>{item.summary}</p>}
    </a>
  )
}

export function News() {
  const { data, isLoading } = useNews()
  if (isLoading || !data) return <TableSkeleton rows={6} />

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>News</h2>
          <span className="shead__link" style={{ color: 'var(--ink-3)' }}>Sky Sports</span>
        </div>

        {data.sky.length === 0 ? (
          <Empty title="No headlines yet">
            <p>{data.empty_message}</p>
          </Empty>
        ) : (
          <div className="fx">
            {data.sky.map((item) => (
              <Story key={item.url} item={item} />
            ))}
          </div>
        )}
        <StaleNote freshness={data.freshness} label="Headlines" />

        <hr className="rule" style={{ margin: '48px 0' }} />

        <div className="tiles tiles--fit">
          <div className="tile">
            <h3>Video</h3>
            <p style={{ marginTop: 14 }}>{data.youtube_message}</p>
          </div>
          <div className="tile">
            <h3>The Athletic</h3>
            <p style={{ marginTop: 14 }}>{data.athletic_message}</p>
          </div>
        </div>
      </div>
    </section>
  )
}
