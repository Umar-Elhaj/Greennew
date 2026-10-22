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
import { setRole } from './helpers';

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
  { id: 'green-data', path: '/green-data', auth: true },
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
/** Fonts and map tiles come from third parties; scripts are vendored and must load. */
function isThirdParty(url: string): boolean {
  try {
    return /(^|\.)(fonts\.googleapis\.com|fonts\.gstatic\.com|tile\.openstreetmap\.org|arcgisonline\.com)$/
      .test(new URL(url).hostname);
  } catch { return false; }
}
function flatten(obj: any, prefix = '', out: Record<string, string> = {}) {
  for (const [k, v] of Object.entries(obj)) {
    if (v && typeof v === 'object') flatten(v, `${prefix}${k}.`, out);
    else out[`${prefix}${k}`] = String(v);
  }
  return out;
}

const DICT_JS = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'translations.js'), 'utf8');
const DICT = JSON.parse(DICT_JS.slice(DICT_JS.indexOf('{'), DICT_JS.lastIndexOf('}') + 1));
const EN = flatten(DICT.en || {});
const FR = flatten(DICT.fr || {});
// English-only values: present in `en`, different from their `fr` translation.
const ENGLISH_ONLY = new Set(
  Object.keys(EN)
    .filter((k) => FR[k] !== undefined && EN[k].trim() !== FR[k].trim())
    .map((k) => EN[k].trim())
    .filter((v) => /[A-Za-z]{3,}/.test(v) && !v.includes('{{')),
);

// Words that betray a string left in the other language (hard-coded in JS
// templates, server messages…). Whole words, case-insensitive.
const WRONG_LANG_WORDS: Record<string, RegExp> = {
  fr: /\b(the|your|you|with|from|please|loading|click|select|upload|history|settings|dashboard|no data|field|fields|disease detected|healthy|unknown|view|save|cancel|delete|search)\b/i,
  en: /\b(les|des|du|vos|votre|avec|pour|aucune?|chargement|parcelles?|maladies?|enregistrer|annuler|supprimer|rechercher|semaine|résultats?)\b/i,
};
// Visible strings allowed to match WRONG_LANG_WORDS (proper nouns, scientific names…).
const WRONG_LANG_ALLOW: RegExp[] = [/^GREEN( Map| Data)?$/, /^GreenBot$/, /Esri|OpenStreetMap|Leaflet|Chart\.js/];

let session: { token: string; user: any } | null = null;


/** 16×16 PNG of one colour, built without dependencies. */
function solidPng(hex: string): Buffer {
  const zlib = require('zlib');
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array(16).fill([r, g, b]).flat())]);
  const raw = Buffer.concat(Array(16).fill(row));
  const crcTable = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (buf: Buffer) => {
    let c = 0xffffffff;
    for (const x of buf) c = crcTable[(c ^ x) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (type: string, data: Buffer) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type), data]);
    const c = Buffer.alloc(4); c.writeUInt32BE(crc(td));
    return Buffer.concat([len, td, c]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(16, 0); ihdr.writeUInt32BE(16, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0)),
  ]);
}

async function ensureUser(request: APIRequestContext) {
  if (session) return session;
  const phone = `+2376${Date.now().toString().slice(-8)}`;
  const r = await request.post('/api/auth/register', {
    data: { first_name: 'E2E', last_name: 'Tester', phone, password: 'secret123', region: 'Centre' },
  });
  expect(r.status(), await r.text()).toBe(201);
  const body = await r.json();
  session = { token: body.access_token, user: body.user };
  // A few analyses (fake model, see E2E_FAKE_MODEL) so lists and charts have data
  for (const color of ['#2a8a3a', '#8a6a2a', '#c04030']) {
    const up = await request.post('/api/camera/upload', {
      headers: { Authorization: `Bearer ${body.access_token}` },
      multipart: { file: { name: 'leaf.png', mimeType: 'image/png', buffer: solidPng(color) } },
    });
    expect(up.status(), await up.text()).toBe(200);
  }
  // …and a parcel, so GREEN Map renders real geometry
  const ring = [[11.5, 3.85], [11.5006, 3.85], [11.5006, 3.8503], [11.5, 3.8503], [11.5, 3.85]];
  const pr = await request.post('/api/parcels', {
    headers: { Authorization: `Bearer ${body.access_token}` },
    data: { name: 'E2E-1', crop_type: 'Maize', geometry: { type: 'Polygon', coordinates: [ring] } },
  });
  expect(pr.status(), await pr.text()).toBe(201);
  // partner role, so GREEN Data is reachable (it is empty: no consented analysis yet)
  setRole(phone, 'partner');
  const me = await request.get('/api/auth/me', { headers: { Authorization: `Bearer ${body.access_token}` } });
  session.user = await me.json();
  return session;
}

async function prime(page: Page, lang: string, auth: boolean, s: { token: string; user: any }) {
  await page.addInitScript(
    ([lang, token, user, auth]) => {
      try {
        localStorage.setItem('green_lang', lang as string);
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
            // The browser logs every failed fetch; expected ones are not problems,
            // nor third-party resources (fonts, map tiles) whose failure changes nothing.
            const src = msg.location()?.url || '';
            if (/Failed to load resource/.test(msg.text())
                && (EXPECTED_HTTP_ERRORS.some((e) => e.url.test(src)) || isThirdParty(src))) return;
            problems.push(`console.error: ${msg.text()}`);
          });
          page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));
          page.on('response', (res) => {
            const status = res.status();
            if (status < 400) return;
            const url = res.url();
            if (isThirdParty(url)) return;
            if (EXPECTED_HTTP_ERRORS.some((e) => e.status === status && e.url.test(url))) return;
            problems.push(`HTTP ${status} ${url}`);
          });

          await page.goto(p.path, { waitUntil: 'networkidle' });
          // Unauthenticated pages may redirect; authenticated ones must not bounce to login.
          if (p.auth) expect(new URL(page.url()).pathname, 'redirected to login').not.toBe('/');

          const dir = path.join(__dirname, 'screenshots', lang, vpName);
          fs.mkdirSync(dir, { recursive: true });
          await page.screenshot({ path: path.join(dir, `${p.id}.png`), fullPage: true });

          const texts = await visibleTexts(page);
          if (lang === 'fr') {
            const leaked = [...new Set(texts.filter((t) => ENGLISH_ONLY.has(t)))];
            for (const t of leaked) problems.push(`english text in fr: "${t}"`);
          }
          const suspicious = [...new Set(texts.filter(
            (t) => WRONG_LANG_WORDS[lang].test(t) && !WRONG_LANG_ALLOW.some((re) => re.test(t)),
          ))];
          for (const t of suspicious) problems.push(`wrong-language text in ${lang}: "${t.slice(0, 80)}"`);
          expect(await page.evaluate(() => document.documentElement.lang)).toBe(lang);

          // No horizontal page scroll at phone width.
          if (vpName === 'mobile') {
            const overflow = await page.evaluate(
              () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
            );
            if (overflow > 1) {
              const culprits = await page.evaluate(() => {
                const W = document.documentElement.clientWidth;
                const out: string[] = [];
                document.querySelectorAll('body *').forEach((el) => {
                  const r = el.getBoundingClientRect();
                  // innermost elements sticking out on the right
                  if (r.right > W + 1 && r.width > 0 && !Array.from(el.children).some(
                    (c) => c.getBoundingClientRect().right > W + 1)) {
                    out.push(`${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]}#${el.id}`);
                  }
                });
                return [...new Set(out)].slice(0, 5);
              });
              problems.push(`horizontal overflow: ${overflow}px (${culprits.join(', ')})`);
            }
          }

          expect(problems, problems.join('\n')).toEqual([]);
        });
      }
    });
  }
}
