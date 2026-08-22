import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useMe } from '@/api/queries'
import { useStaleSessionRecovery } from '@/api/useStaleSessionRecovery'
import { useLiveStream } from '@/api/useLiveStream'
import { Nav } from '@/components/Nav'
import { TableSkeleton } from '@/components/states'
import { Home } from '@/routes/Home'
import { Login } from '@/routes/Login'
import { Placeholder } from '@/routes/Placeholder'

// Route-level code splitting: the picker's logic and the chart library stay off
// the home page's critical path.
const Stats = lazy(() => import('@/routes/Stats').then((m) => ({ default: m.Stats })))
const League = lazy(() => import('@/routes/League').then((m) => ({ default: m.League })))
const Predictions = lazy(() =>
  import('@/routes/Predictions').then((m) => ({ default: m.Predictions })),
)
const Admin = lazy(() => import('@/routes/Admin').then((m) => ({ default: m.Admin })))
const Fpl = lazy(() => import('@/routes/Fpl').then((m) => ({ default: m.Fpl })))
const Watch = lazy(() => import('@/routes/Watch').then((m) => ({ default: m.Watch })))
const News = lazy(() => import('@/routes/News').then((m) => ({ default: m.News })))
const Calendar = lazy(() => import('@/routes/Calendar').then((m) => ({ default: m.Calendar })))
const Archive = lazy(() => import('@/routes/Archive').then((m) => ({ default: m.Archive })))
const Chat = lazy(() => import('@/routes/Chat').then((m) => ({ default: m.Chat })))
const PredictionPicker = lazy(() =>
  import('@/routes/PredictionPicker').then((m) => ({ default: m.PredictionPicker })),
)

export function App() {
  const { data: me, isLoading, error } = useMe()
  useStaleSessionRecovery()
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
            <Route path="/table" element={<League />} />
            <Route path="/stats" element={<Stats />} />
            {/* Kept so existing links and bookmarks still land somewhere sensible. */}
            <Route path="/fixtures" element={<Navigate to="/table?view=matches" replace />} />
            <Route path="/predictions" element={<Predictions />} />
            <Route path="/predictions/build" element={<PredictionPicker />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="/leaderboard" element={<Navigate to="/predictions" replace />} />
            <Route path="/fpl" element={<Fpl />} />
            <Route path="/watch" element={<Watch />} />
            <Route path="/news" element={<News />} />
            <Route path="/calendar" element={<Calendar />} />
            <Route path="/archive" element={<Archive />} />
            <Route path="/chat" element={<Chat />} />
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
