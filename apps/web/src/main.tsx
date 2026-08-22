import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { App } from './App'
import { redirectToCanonicalOrigin } from './api/client'
import './styles/tokens.css'
import './styles/app.css'

const client = new QueryClient({
  defaultOptions: {
    queries: {
      // The stream pushes changes, so aggressive refetching is wasted work.
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => {
        // Never retry an auth failure -- it will not succeed and it delays the
        // login screen the user actually needs.
        if (error instanceof Error && error.name === 'ApiError') return false
        return count < 2
      },
    },
  },
})

// If this build is being served from an origin that is not the api's, hand
// over before rendering. Anything rendered here would be unable to hold a
// session on iOS anyway.
if (redirectToCanonicalOrigin()) {
  // The browser is already navigating; do not mount.
} else {

const root = document.getElementById('root')
if (!root) throw new Error('#root is missing from index.html')

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)

}
