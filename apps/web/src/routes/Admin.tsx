import { useAdminStatus } from '@/api/queries'
import { describeAge, TableSkeleton } from '@/components/states'

export function Admin() {
  const { data, isLoading } = useAdminStatus()
  if (isLoading || !data) return <TableSkeleton rows={8} />

  return (
    <section className="section">
      <div className="wrap">
        <div className="shead">
          <h2>Admin</h2>
          <span className="shead__link" style={{ color: 'var(--ink-3)' }}>{data.environment}</span>
        </div>

        <h3 style={{ fontSize: 13, textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 12 }}>
          Upstream quotas
        </h3>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Source</th>
                <th scope="col">Window</th>
                <th scope="col">Used</th>
                <th scope="col">Budget</th>
                <th scope="col">Left</th>
              </tr>
            </thead>
            <tbody>
              {data.quotas.map((q) => (
                <tr key={q.source}>
                  <td>
                    <b>{q.source}</b>
                  </td>
                  <td className="sec">{q.window}</td>
                  <td className="sec">{q.used}</td>
                  <td className="sec">{q.budget}</td>
                  <td className="pts">{q.remaining}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.quotas.map((q) => (
          <p className="tnote" key={q.source}>
            <b>{q.source}:</b> {q.note}
          </p>
        ))}

        <h3 style={{ fontSize: 13, textTransform: 'uppercase', color: 'var(--ink-3)', margin: '40px 0 12px' }}>
          Cache ages
        </h3>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Payload</th>
                <th scope="col">Source</th>
                <th scope="col">Age</th>
              </tr>
            </thead>
            <tbody>
              {data.caches.map((c) => (
                <tr key={c.name}>
                  <td>
                    <b>{c.name}</b>
                  </td>
                  <td className="sec">{c.source}</td>
                  <td className="sec" style={{ color: c.stale ? 'var(--amber)' : undefined }}>
                    {describeAge(c.age_seconds)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {data.missing_keys.length > 0 && (
          <>
            <h3 style={{ fontSize: 13, textTransform: 'uppercase', color: 'var(--ink-3)', margin: '40px 0 12px' }}>
              Missing keys
            </h3>
            {data.missing_keys.map((m) => (
              <p className="tnote" key={m}>
                {m}
              </p>
            ))}
          </>
        )}
      </div>
    </section>
  )
}
