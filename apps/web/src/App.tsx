import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'
import { useMe } from '@/api/queries'
import { useLiveStream } from '@/api/useLiveStream'
import { Nav } from '@/components/Nav'
import { TableSkeleton } from '@/components/states'
import { Home } from '@/routes/Home'
import { Login } from '@/routes/Login'
import { Placeholder } from '@/routes/Placeholder'

// Route-level code splitting: the picker's logic and the chart library stay off
// the home page's critical path.
const Table = lazy(() => import('@/routes/Table').then((m) => ({ default: m.Table })))
const Fixtures = lazy(() => import('@/routes/Fixtures').then((m) => ({ default: m.Fixtures })))
const Predictions = lazy(() =>
  import('@/routes/Predictions').then((m) => ({ default: m.Predictions })),
)
const Admin = lazy(() => import('@/routes/Admin').then((m) => ({ default: m.Admin })))
const Fpl = lazy(() => import('@/routes/Fpl').then((m) => ({ default: m.Fpl })))
const Leaderboard = lazy(() =>
  import('@/routes/Leaderboard').then((m) => ({ default: m.Leaderboard })),
)
const PredictionPicker = lazy(() =>
  import('@/routes/PredictionPicker').then((m) => ({ default: m.PredictionPicker })),
)

export function App() {
  const { data: me, isLoading, error } = useMe()
  const stream = useLiveStream(Boolean(me))

  if (isLoading) {
    return (
      <main className="wrap" style={{ paddingTop: 80 }}>
        <TableSkeleton rows={6} />
      </main>
    )
  }

  // Any failure to resolve a session means "sign in", not an error screen.
  if (error || !me) return <Login />

  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Nav me={me} stream={stream} />
      <main id="main">
        <Suspense
          fallback={
            <div className="wrap" style={{ paddingTop: 40 }}>
              <TableSkeleton rows={6} />
            </div>
          }
        >
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/table" element={<Table />} />
            <Route path="/fixtures" element={<Fixtures />} />
            <Route path="/predictions" element={<Predictions />} />
            <Route path="/predictions/build" element={<PredictionPicker />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/leaderboard" element={<Leaderboard />} />
            <Route path="/fpl" element={<Fpl />} />
            <Route
              path="/watch"
              element={
                <Placeholder
                  title="Watch log"
                  blurb="Marking a match watched opens at kick-off and closes twelve hours after full time. Nothing has kicked off yet."
                />
              }
            />
            <Route
              path="/news"
              element={
                <Placeholder
                  title="News"
                  blurb="Sky Sports items and YouTube uploads need their API keys configured. Set them and this fills in without a redeploy."
                />
              }
            />
            <Route
              path="*"
              element={<Placeholder title="Not found" blurb="That page does not exist." />}
            />
          </Routes>
        </Suspense>
      </main>
      <footer className="footer">
        <div className="wrap">
          Prediction League {me.season}. Times shown in each person&rsquo;s own timezone.
          Broadcast listings verified 21 August 2026.
        </div>
      </footer>
    </>
  )
}
