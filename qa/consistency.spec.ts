/**
 * GREEN — cross-page consistency (lot 8.2): same shell, language switch,
 * theme, no dead internal link, colour contrast (axe-core, WCAG 2 AA).
 */
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { setRole } from './helpers';

const APP_PAGES = ['/dashboard', '/map', '/camera', '/chatbot', '/diseases', '/calendar', '/economics', '/benchmark',
  '/marketplace', '/history', '/settings', '/profile', '/green-data'];
const PUBLIC_PAGES = ['/', '/register'];

let auth: { token: string; user: any };

test.beforeAll(async ({ request }) => {
  const phone = `+2376${Date.now().toString().slice(-8)}`;
  const r = await request.post('/api/auth/register', { data: { first_name: 'Cons', last_name: 'Check', phone, password: 'secret123' } });
  const b = await r.json();
  setRole(phone, 'partner');
  const me = await (await request.get('/api/auth/me', { headers: { Authorization: `Bearer ${b.access_token}` } })).json();
  auth = { token: b.access_token, user: me };
});

for (const theme of ['light', 'dark']) {
  for (const path of [...PUBLIC_PAGES, ...APP_PAGES]) {
    test(`${path} [${theme}]: shell, links, contrast`, async ({ page, request }) => {
      const isApp = APP_PAGES.includes(path);
      await page.addInitScript(([t, u, th, app]) => {
        localStorage.setItem('green_lang', 'fr');
        localStorage.setItem('green_theme', th as string);
        if (app) { localStorage.setItem('green_token', t as string); localStorage.setItem('green_user', u as string); }
      }, [auth.token, JSON.stringify(auth.user), theme, isApp] as const);
      await page.goto(path, { waitUntil: 'networkidle' });

      // theme applied before paint, same rule everywhere
      expect(await page.evaluate(() => document.documentElement.getAttribute('data-theme'))).toBe(theme);
      // language switch on every page; app pages share the same header and navigation
      await expect(page.locator('.lang-switch-btn[data-lang="fr"]')).toBeVisible();
      if (isApp) {
        await expect(page.locator('#appHeader')).toHaveCount(1);
        expect(await page.locator('#sidebarNav .nav-item').count()).toBe(12);   // 11 pages + GREEN Data (partner)
        await expect(page.locator('#headerPageTitle')).not.toBeEmpty();
      }

      // no dead internal link
      const hrefs = await page.evaluate(() => [...new Set([...document.querySelectorAll('a[href]')]
        .map(a => (a as HTMLAnchorElement).href).filter(h => h.startsWith(location.origin)))]);
      for (const href of hrefs) {
        const res = await request.get(href, { maxRedirects: 2 });
        expect(res.status(), `dead link ${href} on ${path}`).toBeLessThan(400);
      }

      // colour contrast of text (WCAG 2 AA); map tiles and charts are excluded (images)
      const results = await new AxeBuilder({ page }).withRules(['color-contrast'])
        .exclude('.leaflet-container').exclude('canvas').analyze();
      const issues = results.violations.flatMap(v => v.nodes.map(n => `${n.target.join(' ')} — ${n.any[0]?.message || ''}`));
      expect(issues, issues.join('\n')).toEqual([]);
    });
  }
}
