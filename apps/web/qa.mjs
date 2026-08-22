/**
 * End-to-end QA sweep.
 *
 * Drives the real app in three engines at two viewports and asserts the things
 * that unit tests structurally cannot: that every route actually renders, that
 * nothing leaks a raw error or an `undefined` into the page, that the layout
 * never scrolls sideways on a phone, and that the interactive bits open.
 *
 * Run it repeatedly (`--rounds 3`) — flaky failures are the ones worth finding,
 * and a suite that only ever runs once cannot see them.
 *
 *   node qa.mjs                          # localhost, chromium, 1 round
 *   node qa.mjs --rounds 3 --all-engines
 *   node qa.mjs --url https://league-api-i6u5.onrender.com
 */

import { chromium, firefox, webkit } from 'playwright'

const arg = (flag, fallback) => {
  const i = process.argv.indexOf(flag)
  return i === -1 ? fallback : process.argv[i + 1]
}
const has = (flag) => process.argv.includes(flag)

const APP = arg('--url', 'http://localhost:5173')
const CODE = arg('--code', 'lviv-gooner')
const ROUNDS = Number(arg('--rounds', '1'))
const ENGINES = has('--all-engines')
  ? [['chromium', chromium], ['webkit', webkit], ['firefox', firefox]]
  : [['chromium', chromium]]

const ROUTES = [
  '/', '/table', '/table?view=projected', '/table?view=matches', '/stats',
  '/predictions', '/fpl', '/watch', '/news', '/calendar', '/chat', '/archive', '/admin',
]

const VIEWPORTS = [
  ['desktop', { width: 1280, height: 900 }],
  ['phone', { width: 390, height: 844 }],
]

/* Both themes. A colour token can be correct in one and unreadable in the
   other, and only one of those gets looked at by eye. */
const SCHEMES = has('--light-only') ? ['light'] : ['light', 'dark']

// Strings that should never reach a user's screen.
const LEAKS = [
  'undefined', 'NaN', '[object Object]', 'Internal Server Error',
  'Traceback', 'TypeError', 'Cannot read', 'null null',
  // Escaped markup that got decoded back into visible tags. The Guardian
  // escapes the HTML inside its feed descriptions, and a strip-then-decode
  // ordering turned "&lt;p&gt;" into a literal <p> on the news page.
  '<p>', '<br>', '<a href', '</a>', '&lt;', '&amp;', '&quot;', '&#39;',
]

/**
 * Console noise this harness causes rather than finds. Kept narrow on purpose
 * — a broad filter would hide the failures worth catching.
 *
 * - 401 before sign-in is the app correctly refusing an anonymous request.
 * - 429 is the SSE cap (4 concurrent streams per person, see auth.py) doing
 *   its job: this sweep opens eighteen browser contexts as the same person,
 *   which no real user does. The cap releases correctly in a `finally`.
 * - The ServiceWorker and /api/stream errors are teardown artifacts — a
 *   context closing mid-navigation aborts the in-flight fetch and the SSE
 *   reconnect. Firefox reports both loudly; neither survives the page.
 */
const IGNORE = [
  /\b401\b/,
  /favicon/,
  /\b429\b/,
  /Too Many Requests/,
  /ServiceWorker intercepted the request/,
  /establish a connection to the server at .*\/api\/stream/,
  /NetworkError when attempting to fetch/,
]

const problems = []
let checks = 0
const check = (ok, label) => {
  checks++
  if (!ok) problems.push(label)
}

async function signIn(page) {
  await page.goto(APP, { waitUntil: 'domcontentloaded', timeout: 60000 })
  // Wait for React to decide which of the two it is rendering. Checking for
  // the login field at domcontentloaded finds nothing, skips the sign-in, and
  // then times out waiting for a nav that was never going to appear.
  await page.waitForSelector('input#code, .nav', { timeout: 60000 })
  const code = page.locator('input#code')
  if (await code.count()) {
    await code.fill(CODE)
    await page.click('button[type=submit]')
  }
  await page.waitForSelector('.nav', { timeout: 60000 })
}

async function sweep(engineName, engine, viewportName, viewport, round, scheme) {
  const tag = `${engineName}/${viewportName}/${scheme} r${round}`
  const browser = await engine.launch()
  const context = await browser.newContext({ viewport, colorScheme: scheme })
  const page = await context.newPage()

  const consoleErrors = []
  page.on('pageerror', (e) => consoleErrors.push(`${tag} pageerror: ${e.message.slice(0, 120)}`))
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    const t = m.text()
    if (IGNORE.some((re) => re.test(t))) return
    consoleErrors.push(`${tag} console: ${t.slice(0, 120)}`)
  })

  try {
    await signIn(page)

    for (const route of ROUTES) {
      await page.goto(`${APP}${route}`, { waitUntil: 'networkidle', timeout: 60000 })
      await page.waitForTimeout(600)
      const where = `${tag} ${route}`

      // Something rendered, and it is not the 404 placeholder.
      const heading = await page.locator('h1, h2').first().innerText().catch(() => '')
      check(heading.trim().length > 0, `${where}: no heading rendered`)
      check(!heading.includes('Not found'), `${where}: fell through to the 404 page`)

      // The page must never scroll sideways — three of the four are on phones.
      const overflow = await page.evaluate(() => ({
        doc: document.documentElement.scrollWidth,
        win: window.innerWidth,
      }))
      check(
        overflow.doc <= overflow.win + 1,
        `${where}: horizontal overflow ${overflow.doc} > ${overflow.win}`,
      )

      // No raw error text, and no placeholder that leaked from a null.
      const body = await page.locator('main').innerText().catch(() => '')
      for (const bad of LEAKS) {
        check(!body.includes(bad), `${where}: leaked "${bad}" into the page`)
      }

      // Every image that rendered actually loaded.
      const broken = await page.evaluate(() =>
        [...document.images].filter((i) => i.complete && i.naturalWidth === 0).map((i) => i.src),
      )
      check(broken.length === 0, `${where}: broken image(s) ${broken.slice(0, 2).join(', ')}`)

      // Every run of text must clear WCAG AA against whatever it actually sits
      // on. Computed at runtime rather than reasoned about in the stylesheet,
      // because the ground a token lands on depends on where it is used --
      // brand blue passes on white and fails on the tinted panel.
      const contrast = await page.evaluate(() => {
        const bad = []
        const lum = (r, g, b) => {
          const f = (v) => {
            v /= 255
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)
          }
          return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
        }
        const parse = (s) => {
          const m = s.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?/)
          return m ? { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] } : null
        }
        for (const el of document.querySelectorAll('main *, .tabbar *, .nav *')) {
          if (!el.textContent?.trim() || el.children.length) continue
          // Crests are club brand colours, aria-hidden, and the club name is
          // always rendered beside them.
          if (el.classList.contains('crest')) continue
          const s = getComputedStyle(el)
          const fg = parse(s.color)
          if (!fg) continue
          let bg = null
          let n = el
          while (n) {
            const c = parse(getComputedStyle(n).backgroundColor)
            if (c && c.a > 0.9) { bg = c; break }
            n = n.parentElement
          }
          if (!bg) continue
          const L1 = lum(fg.r, fg.g, fg.b)
          const L2 = lum(bg.r, bg.g, bg.b)
          const ratio = (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05)
          const size = parseFloat(s.fontSize)
          const bold = parseInt(s.fontWeight) >= 600
          const min = size >= 24 || (size >= 18.66 && bold) ? 3 : 4.5
          if (ratio < min) {
            bad.push(`${(el.className || el.tagName).toString().slice(0, 26)} ${ratio.toFixed(2)}:1 needs ${min}`)
          }
        }
        return [...new Set(bad)].slice(0, 3)
      })
      check(contrast.length === 0, `${where}: contrast ${contrast.join(' | ')}`)

      // Buttons need an accessible name, or a screen reader announces "button".
      const nameless = await page.evaluate(() =>
        [...document.querySelectorAll('button')].filter(
          (b) => !b.textContent.trim() && !b.getAttribute('aria-label') && !b.getAttribute('title'),
        ).length,
      )
      check(nameless === 0, `${where}: ${nameless} button(s) with no accessible name`)
    }

    // --- interactive checks, desktop only (hover-dependent affordances) ---
    if (viewportName === 'desktop') {
      await page.goto(`${APP}/table?view=matches`, { waitUntil: 'networkidle', timeout: 60000 })
      await page.waitForTimeout(500)

      const lineups = page.locator('.match__actions button', { hasText: 'Line-ups' }).first()
      if (await lineups.count()) {
        await lineups.click()
        await page.waitForSelector('.lineups, .tnote', { timeout: 20000 })
        const panel = await page.locator('.lineups').count()
        const note = await page.locator('.tnote').first().innerText().catch(() => '')
        check(
          panel > 0 || note.length > 0,
          `${tag} line-ups: opened but rendered neither an XI nor an explanation`,
        )
        if (panel > 0) {
          const xi = await page.locator('.lineups .lineup-side__players li').count()
          check(xi >= 11, `${tag} line-ups: only ${xi} players rendered, expected at least 11`)
          const basis = await page.locator('.lineups__basis').count()
          check(basis > 0, `${tag} line-ups: an XI rendered with no confirmed/predicted label`)
        }
      }

      const where = page.locator('.match__actions button', { hasText: 'Where' }).first()
      if (await where.count()) {
        await where.click()
        await page.waitForTimeout(400)
        const cities = await page.locator('.tv__cell').count()
        check(cities >= 4, `${tag} where: expected four cities, got ${cities}`)
      }

      await page.goto(`${APP}/calendar`, { waitUntil: 'networkidle', timeout: 60000 })
      await page.waitForTimeout(500)
      const rows = await page.locator('.cal-row').count()
      check(rows > 0, `${tag} calendar: no events rendered`)
      const watch = await page.locator('.cal-watch__cell').count()
      check(watch > 0, `${tag} calendar: no where-to-watch listings rendered`)
      const chips = page.locator('.source-filter .chip')
      if ((await chips.count()) > 1) {
        await chips.nth(1).click()
        await page.waitForTimeout(300)
        const after = await page.locator('.cal-row').count()
        check(after > 0, `${tag} calendar: filtering by sport emptied the list`)
        check(after <= rows, `${tag} calendar: filter increased the row count`)
      }
    }

    for (const e of consoleErrors) problems.push(e)
  } finally {
    await browser.close()
  }
}

const started = Date.now()
for (let round = 1; round <= ROUNDS; round++) {
  for (const [name, engine] of ENGINES) {
    for (const [vpName, vp] of VIEWPORTS) {
      for (const scheme of SCHEMES) {
        await sweep(name, engine, vpName, vp, round, scheme)
      }
    }
  }
  console.log(`round ${round}/${ROUNDS} done — ${checks} checks, ${problems.length} problems so far`)
}

const seconds = ((Date.now() - started) / 1000).toFixed(0)
console.log(`\n${checks} checks in ${seconds}s across ${ENGINES.length} engine(s) × ${VIEWPORTS.length} viewport(s) × ${SCHEMES.length} theme(s) × ${ROUNDS} round(s)`)
if (problems.length === 0) {
  console.log('QA CLEAN')
} else {
  const unique = [...new Set(problems)]
  console.log(`\n${problems.length} problem(s), ${unique.length} distinct:`)
  for (const p of unique) console.log(`  - ${p}`)
  process.exit(1)
}
