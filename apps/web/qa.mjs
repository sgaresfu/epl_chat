import { chromium, webkit, firefox } from 'playwright'

const APP = 'https://league-api-i6u5.onrender.com'
const ROUTES = ['/', '/table', '/table?view=projected', '/table?view=matches', '/stats',
                '/predictions', '/fpl', '/watch', '/news', '/chat', '/admin']

const problems = []
let checks = 0
function check(cond, label) {
  checks++
  if (!cond) problems.push(label)
}

async function sweep(engineName, engine, opts, round) {
  const browser = await engine.launch()
  const ctx = await browser.newContext(opts)
  const page = await ctx.newPage()
  const consoleErrors = []
  page.on('pageerror', (e) => consoleErrors.push(`${engineName}: ${e.message}`))
  page.on('console', (m) => {
    if (m.type() === 'error' && !m.text().includes('401') && !m.text().includes('favicon'))
      consoleErrors.push(`${engineName}: ${m.text().slice(0, 90)}`)
  })

  await page.goto(APP, { waitUntil: 'networkidle', timeout: 120000 })
  await page.fill('input#code', 'lviv-gooner')
  await page.click('button[type=submit]')
  await page.waitForSelector('.nav', { timeout: 60000 })

  for (const route of ROUTES) {
    await page.goto(`${APP}${route}`, { waitUntil: 'networkidle', timeout: 60000 })
    await page.waitForTimeout(1400)

    const heading = await page.locator('h1, h2').first().innerText().catch(() => '')
    check(heading.length > 0, `${engineName} r${round} ${route}: no heading`)

    // Nothing should scroll the page body sideways.
    const o = await page.evaluate(() => ({ d: document.documentElement.scrollWidth, w: window.innerWidth }))
    check(o.d <= o.w + 1, `${engineName} r${round} ${route}: horizontal overflow ${o.d}>${o.w}`)

    // No raw error text should ever reach the user.
    const body = await page.locator('body').innerText()
    for (const bad of ['undefined', 'NaN', '[object Object]', 'Internal Server Error', 'Traceback']) {
      check(!body.includes(bad), `${engineName} r${round} ${route}: shows "${bad}"`)
    }

    // Images must load.
    const imgs = await page.evaluate(() =>
      [...document.querySelectorAll('img')].filter((i) => i.complete && i.naturalWidth === 0).length)
    check(imgs === 0, `${engineName} r${round} ${route}: ${imgs} broken images`)

    // Every button must be reachable and adequately sized for a thumb.
    const small = await page.evaluate(() =>
      [...document.querySelectorAll('button:not([disabled])')]
        .map((b) => b.getBoundingClientRect())
        .filter((r) => r.width > 0 && r.height > 0 && r.height < 28).length)
    check(small === 0, `${engineName} r${round} ${route}: ${small} buttons under 28px tall`)
  }

  check(consoleErrors.length === 0, `${engineName} r${round}: console errors -> ${consoleErrors.slice(0,2).join(' | ')}`)
  await browser.close()
}

const ENGINES = [
  ['Chromium', chromium, { viewport: { width: 1280, height: 900 } }],
  ['Safari', webkit, { viewport: { width: 1280, height: 900 } }],
  ['Firefox', firefox, { viewport: { width: 1280, height: 900 } }],
  ['iPhone', webkit, { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }],
]

for (const round of [1, 2, 3]) {
  for (const [name, engine, opts] of ENGINES) {
    await sweep(name, engine, opts, round)
    process.stdout.write('.')
  }
  console.log(`  round ${round} done`)
}

console.log(`\n${checks} checks, ${problems.length} problems`)
if (problems.length) {
  const unique = [...new Set(problems)]
  console.log(unique.slice(0, 25).map((p) => '  ' + p).join('\n'))
}
