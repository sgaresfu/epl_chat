import '@testing-library/jest-dom/vitest'

// jsdom has no EventSource, and the live-stream hook opens one on mount.
class MockEventSource {
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  addEventListener(): void {}
  removeEventListener(): void {}
  close(): void {}
}
globalThis.EventSource = MockEventSource as unknown as typeof EventSource
