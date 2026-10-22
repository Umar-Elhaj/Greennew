/**
 * GREEN — functional flows (grows into the lot 8 reference journey).
 */
import { test, expect, Page, APIRequestContext } from '@playwright/test';

async function newUser(request: APIRequestContext) {
  const phone = `+2376${Date.now().toString().slice(-8)}`;
  const r = await request.post('/api/auth/register', {
    data: { first_name: 'Flow', last_name: 'User', phone, password: 'secret123', region: 'Littoral' },
  });
  expect(r.status()).toBe(201);
  const body = await r.json();
  return { token: body.access_token as string, user: body.user, phone };
}

/** 16×16 PNG of one colour (same helper as e2e.spec.ts). */
function solidPng(hex: string): Buffer {
  const zlib = require('zlib');
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array(16).fill([r, g, b]).flat())]);
  const raw = Buffer.concat(Array(16).fill(row));
  const table = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (buf: Buffer) => { let c = 0xffffffff; for (const x of buf) c = table[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (type: string, data: Buffer) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type), data]);
    const c = Buffer.alloc(4); c.writeUInt32BE(crc(td));
    return Buffer.concat([len, td, c]);
  };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(16, 0); ihdr.writeUInt32BE(16, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

async function upload(request: APIRequestContext, token: string, color: string) {
  const r = await request.post('/api/camera/upload', {
    headers: { Authorization: `Bearer ${token}` },
    multipart: { file: { name: 'leaf.png', mimeType: 'image/png', buffer: solidPng(color) } },
  });
  expect(r.status()).toBe(200);
  return r.json();
}

async function signIn(page: Page, s: { token: string; user: any }, lang = 'fr') {
  await page.addInitScript(([t, u, l]) => {
    localStorage.setItem('green_token', t);
    localStorage.setItem('green_user', u);
    if (!localStorage.getItem('green_lang_set_by_test')) {
      localStorage.setItem('green_lang', l);
      localStorage.setItem('green_lang_set_by_test', '1');
    }
  }, [s.token, JSON.stringify(s.user), lang]);
}

test('language switch applies without reloading the page', async ({ page, request }) => {
  const s = await newUser(request);
  await signIn(page, s, 'fr');
  await page.goto('/dashboard');
  await expect(page.locator('#headerPageTitle')).toHaveText('Tableau de bord');
  await page.evaluate(() => { (window as any).__marker = 42; });
  await page.locator('#appHeader .lang-switch-btn[data-lang="en"]').click();
  await expect(page.locator('#headerPageTitle')).toHaveText('Dashboard');
  await expect(page.locator('.nav-item[data-page="history"] .nav-item-label')).toHaveText('Analysis history');
  expect(await page.evaluate(() => (window as any).__marker)).toBe(42);   // same document
  expect(await page.evaluate(() => document.documentElement.lang)).toBe('en');
  // and the choice survives a reload
  await page.reload();
  await expect(page.locator('#headerPageTitle')).toHaveText('Dashboard');
});

test('register in French then sign in', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('green_lang', 'fr'));
  await page.goto('/register');
  const phone = `69${Date.now().toString().slice(-7)}`;
  await page.fill('#first_name', 'Awa');
  await page.fill('#last_name', 'Ngono');
  await page.fill('#phone', phone);
  await page.click('#registerNextBtn');
  await page.selectOption('#region', 'Ouest');
  await page.fill('#password', 'motdepasse1');
  await page.fill('#confirm_password', 'autre');
  await page.click('#registerSubmitBtn');
  await expect(page.locator('#confirm_password_error')).toHaveText('Les mots de passe ne correspondent pas.');
  await page.fill('#confirm_password', 'motdepasse1');
  await page.check('#dataset_consent');
  await page.click('#registerSubmitBtn');
  await page.waitForURL('**/dashboard');
  const user = await page.evaluate(() => JSON.parse(localStorage.getItem('green_user') || '{}'));
  expect(user.region).toBe('Ouest');
  expect(user.dataset_consent).toBe(true);
});

test('consent toggles are stored on the server', async ({ page, request }) => {
  const s = await newUser(request);
  await signIn(page, s);
  await page.goto('/settings');
  await page.locator('label.toggle-wrap:has(#toggleLocation)').click();
  await expect(page.getByText('Préférence enregistrée.')).toBeVisible();
  const me = await request.get('/api/auth/me', { headers: { Authorization: `Bearer ${s.token}` } });
  expect((await me.json()).location_consent).toBe(true);
});

test('profile: clearing an optional field and a translated server error', async ({ page, request }) => {
  const s = await newUser(request);
  await signIn(page, s);
  await page.goto('/profile');
  await page.fill('#companyName', 'Ferme Test');
  await page.click('#saveBtn');
  await expect(page.locator('#profileAlert')).toHaveText('Profil mis à jour.');
  await page.fill('#companyName', '');
  await page.click('#saveBtn');
  await expect(page.locator('#infoCompany')).toHaveText('—');
  await page.fill('#currentPwd', 'wrong-password');
  await page.fill('#newPwd', 'nouveau123');
  await page.fill('#confirmPwd', 'nouveau123');
  await page.click('#pwdBtn');
  await expect(page.locator('#pwdAlert')).toHaveText('Le mot de passe actuel est incorrect.');
});

test('disease library: English search in a French UI, detail re-rendered on language switch', async ({ page, request }) => {
  const s = await newUser(request);
  await signIn(page, s);
  await page.goto('/diseases');
  await page.fill('#searchInput', 'tomato');
  await expect(page.locator('.disease-card[data-id="early-blight"]')).toBeVisible();
  await page.click('.disease-card[data-id="early-blight"]');
  await expect(page.locator('.detail-hdr-name')).toHaveText('Alternariose');
  await expect(page.locator('#detailPanel')).toContainText('Actions recommandées');
  await page.locator('#appHeader .lang-switch-btn[data-lang="en"]').click();
  await expect(page.locator('.detail-hdr-name')).toHaveText('Early blight');
  await expect(page.locator('#detailPanel')).toContainText('Recommended actions');
});

test('history: deep link, sheet in both languages, delete', async ({ page, request }) => {
  const s = await newUser(request);
  const up = await upload(request, s.token, '#c04030');
  await signIn(page, s);
  await page.goto(`/history?id=${up.analysis_id}`);
  const sheet = page.locator('#ficheContent');
  await expect(sheet).toContainText('pas un diagnostic');
  await expect(sheet.locator('img.fiche-img')).toBeVisible();
  // the stored image is served (signed URL) and really loads
  expect(await sheet.locator('img.fiche-img').evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await page.locator('#appHeader .lang-switch-btn[data-lang="en"]').click();
  await expect(sheet).toContainText('not a diagnosis');
  page.once('dialog', (d) => d.accept());
  await page.locator(`[data-del="${up.analysis_id}"]`).click();
  await expect(page.locator('#histEmptyText')).toContainText('No analysis yet');
});
