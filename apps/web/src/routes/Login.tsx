/** One screen, one field. */

import { useState, type FormEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '@/api/client'
import { keys } from '@/api/queries'
import type { Me } from '@/api/types'

export function Login() {
  const client = useQueryClient()
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const me = await api.post<Me>('/api/session', { code })
      client.setQueryData(keys.me, me)
      await client.invalidateQueries()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  return (
    <main className="login">
      <div className="login__box">
        <h1>Prediction League</h1>
        <p>Four friends, one season. Enter your code word.</p>
        <form onSubmit={submit}>
          <label className="sr-only" htmlFor="code">
            Code word
          </label>
          <input
            id="code"
            name="code"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Code word"
            autoComplete="current-password"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            required
          />
          <p className="login__error" role="alert">
            {error}
          </p>
          <button className="btn" type="submit" disabled={busy || code.length === 0}>
            {busy ? 'Checking…' : 'Sign in'}
          </button>
        </form>
      </div>
    </main>
  )
}
