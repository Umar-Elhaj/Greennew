/**
 * GREEN — page sweep.
 *
 * Every page × {fr, en} × {1366×768, 390×844}. A page fails when:
 *   - the console logs an error (or the page throws);
 *   - a network response is >= 400 and not in EXPECTED_HTTP_ERRORS;
 *   - in `fr`, a visible text node equals an English dictionary value
 *     whose French translation differs (i.e. something was left in English).
 * Screenshots: qa/screenshots/<lang>/<viewport>/<page>.png
 */
import { test, expect, Page, APIRequestContext } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const PAGES = [
  { id: 'index', path: '/', auth: false },
  { id: 'register', path: '/register', auth: false },
  { id: 'dashboard', path: '/dashboard', auth: true },
  { id: 'map', path: '/map', auth: true },
  { id: 'camera', path: '/camera', auth: true },
  { id: 'chatbot', path: '/chatbot', auth: true },
  { id: 'diseases', path: '/diseases', auth: true },
  { id: 'calendar', path: '/calendar', auth: true },
  { id: 'economics', path: '/economics', auth: true },
  { id: 'benchmark', path: '/benchmark', auth: true },
  { id: 'marketplace', path: '/marketplace', auth: true },
  { id: 'history', path: '/history', auth: true },
  { id: 'settings', path: '/settings', auth: true },
  { id: 'profile', path: '/profile', auth: true },
  ...(fs.existsSync(path.join(__dirname, '..', 'frontend', 'green-data.html'))
    ? [{ id: 'green-data', path: '/green-data', auth: true }]
    : []),
];

const LANGS = ['fr', 'en'] as const;
const VIEWPORTS = {
  desktop: { width: 1366, height: 768 },
  mobile: { width: 390, height: 844 },
};

// Optional services are not configured in e2e: their 503 is the expected,
// user-explained behaviour ("feature disabled"), not a failure.
const EXPECTED_HTTP_ERRORS: Array<{ url: RegExp; status: number }> = [
  { url: /\/api\/weather\//, status: 503 },
];

// ---------------------------------------------------------------- helpers
function flatten(obj: any, prefix = '', out: Record<string, string> = {}) {
  for (const [k, v] of Object.entries(obj)) {
    if (v && typeof v === 'object') flatten(v, `${prefix}${k}.`, out);
    else out[`${prefix}${k}`] = String(v);
  }
  return out;
}

const DICT = JSON.parse(
  fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'translations.json'), 'utf8'),
);
const EN = flatten(DICT.en || {});
const FR = flatten(DICT.fr || {});
// English-only values: present in `en`, different from their `fr` translation.
const ENGLISH_ONLY = new Set(
  Object.keys(EN)
    .filter((k) => FR[k] !== undefined && EN[k].trim() !== FR[k].trim())
    .map((k) => EN[k].trim())
    .filter((v) => /[A-Za-z]{3,}/.test(v) && !v.includes('{{')),
);

let session: { token: string; user: any } | null = null;

async function ensureUser(request: APIRequestContext) {
  if (session) return session;
  const phone = `+2376${Date.now().toString().slice(-8)}`;
  const r = await request.post('/api/auth/register', {
    data: { first_name: 'E2E', last_name: 'Tester', phone, password: 'secret123', region: 'Centre' },
  });
  expect(r.status(), await r.text()).toBe(201);
  const body = await r.json();
  session = { token: body.access_token, user: body.user };
  return session;
}

async function prime(page: Page, lang: string, auth: boolean, s: { token: string; user: any }) {
  await page.addInitScript(
    ([lang, token, user, auth]) => {
      try {
        localStorage.setItem('green_lang', lang as string);
        localStorage.setItem('green_language', lang as string); // legacy key, removed in lot 3
        if (auth) {
          localStorage.setItem('green_token', token as string);
          localStorage.setItem('green_user', JSON.stringify(user));
        } else {
          localStorage.removeItem('green_token');
          localStorage.removeItem('green_user');
        }
      } catch (_) { /* storage blocked: page must still render */ }
    },
    [lang, s.token, s.user, auth] as const,
  );
}

async function visibleTexts(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n: Node | null;
    while ((n = walker.nextNode())) {
      const text = (n.textContent || '').replace(/\s+/g, ' ').trim();
      if (!text) continue;
      const el = n.parentElement;
      if (!el || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(el.tagName)) continue;
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || el.getClientRects().length === 0) continue;
      out.push(text);
    }
    for (const el of Array.from(document.querySelectorAll('[placeholder],[title],[aria-label]'))) {
      for (const a of ['placeholder', 'title', 'aria-label']) {
        const v = el.getAttribute(a);
        if (v && (el as HTMLElement).getClientRects().length) out.push(v.trim());
      }
    }
    return out;
  });
}

// ---------------------------------------------------------------- tests
for (const lang of LANGS) {
  for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
    test.describe(`${lang} @ ${vpName}`, () => {
      test.use({ viewport });

      for (const p of PAGES) {
        test(`${p.id}`, async ({ page, request }) => {
          const s = await ensureUser(request);
          await prime(page, lang, p.auth, s);

          const problems: string[] = [];
          page.on('console', (msg) => {
            if (msg.type() !== 'error') return;
            // The browser logs every failed fetch; expected ones are not problems.
            const src = msg.location()?.url || '';
            if (/Failed to load resource/.test(msg.text()) && EXPECTED_HTTP_ERRORS.some((e) => e.url.test(src))) return;
            problems.push(`console.error: ${msg.text()}`);
          });
          page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));
          page.on('response', (res) => {
            const status = res.status();
            if (status < 400) return;
            const url = res.url();
            if (EXPECTED_HTTP_ERRORS.some((e) => e.status === status && e.url.test(url))) return;
            problems.push(`HTTP ${status} ${url}`);
          });

          await page.goto(p.path, { waitUntil: 'networkidle' });
          // Unauthenticated pages may redirect; authenticated ones must not bounce to login.
          if (p.auth) expect(new URL(page.url()).pathname, 'redirected to login').not.toBe('/');

          const dir = path.join(__dirname, 'screenshots', lang, vpName);
          fs.mkdirSync(dir, { recursive: true });
          await page.screenshot({ path: path.join(dir, `${p.id}.png`), fullPage: true });

          if (lang === 'fr') {
            const leaked = [...new Set((await visibleTexts(page)).filter((t) => ENGLISH_ONLY.has(t)))];
            for (const t of leaked) problems.push(`english text in fr: "${t}"`);
          }

          // No horizontal page scroll at phone width.
          if (vpName === 'mobile') {
            const overflow = await page.evaluate(
              () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
            );
            if (overflow > 1) problems.push(`horizontal overflow: ${overflow}px`);
          }

          expect(problems, problems.join('\n')).toEqual([]);
        });
      }
    });
  }
}
