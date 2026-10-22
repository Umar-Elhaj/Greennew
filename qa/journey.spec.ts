/**
 * GREEN — reference journey (lot 8.1), in French and in English, through the UI:
 * register -> sign out -> sign in -> dashboard -> two parcels (one drawn
 * offline) -> grid -> mission -> analyses (queued offline, tagged with the
 * mission cell) -> history -> field sheet -> heatmap -> GreenBot with the
 * analysis context -> GREEN Data (partner) -> CSV export -> sign out.
 * Expected texts are read from the dictionary, so one test serves both languages.
 */
import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import * as zlib from 'zlib';
import { setRole } from './helpers';

const DICT_JS = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'translations.js'), 'utf8');
const DICT = JSON.parse(DICT_JS.slice(DICT_JS.indexOf('{'), DICT_JS.lastIndexOf('}') + 1));
const tr = (lang: string, key: string, params: Record<string, string | number> = {}) => {
  let v: any = DICT[lang];
  for (const k of key.split('.')) v = v[k];
  return String(v).replace(/\{\{\s*(\w+)\s*\}\}/g, (_, n) => String(params[n] ?? ''));
};

function png(hex: string): Buffer {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array(32).fill([r, g, b]).flat())]);
  const raw = Buffer.concat(Array(32).fill(row));
  const table = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
  const crc = (buf: Buffer) => { let c = 0xffffffff; for (const x of buf) c = table[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
  const chunk = (type: string, data: Buffer) => {
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type), data]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td));
    return Buffer.concat([len, td, c]);
  };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(32, 0); ihdr.writeUInt32BE(32, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

async function drawParcel(page: Page, origin: [number, number], name: string) {
  await page.evaluate(`map.setView([${origin[0]}, ${origin[1]}], 19)`);
  await page.click('#newParcelBtn');
  const box = (await page.locator('#map').boundingBox())!;
  for (const [x, y] of [[180, 140], [440, 140], [440, 330], [180, 330]]) await page.mouse.click(box.x + x, box.y + y);
  await page.click('#finishDrawBtn');
  await page.fill('#fName', name);
  await page.selectOption('#fCrop', 'Maize');
  await page.click('#saveParcelBtn');
}

for (const lang of ['fr', 'en'] as const) {
  test(`reference journey (${lang})`, async ({ page, context, request }) => {
    test.setTimeout(180_000);
    const phone = `69${Date.now().toString().slice(-7)}`;
    const password = 'motdepasse-42';
    await page.addInitScript((l) => { if (!sessionStorage.getItem('lang-set')) { localStorage.setItem('green_lang', l); sessionStorage.setItem('lang-set', '1'); } }, lang);

    // 1. register (with consent) -> dashboard
    await page.goto('/register');
    await expect(page.locator('.auth-greeting')).toHaveText(tr(lang, 'auth.register.greeting'));
    await page.fill('#first_name', 'Nadia');
    await page.fill('#last_name', 'Fotso');
    await page.fill('#phone', phone);
    await page.click('#registerNextBtn');
    await page.selectOption('#region', 'Centre');
    await page.fill('#password', password);
    await page.fill('#confirm_password', password);
    await page.check('#dataset_consent');
    await page.click('#registerSubmitBtn');
    await page.waitForURL('**/dashboard');
    await expect(page.locator('#headerPageTitle')).toHaveText(tr(lang, 'nav.dashboard'));

    // 2. sign out (settings) -> sign in
    await page.goto('/settings');
    await page.locator('button', { hasText: tr(lang, 'common.actions.sign_out') }).click();
    await page.waitForURL((u) => u.pathname === '/');
    await page.fill('#identifier', `+237 ${phone}`);
    await page.fill('#password', password);
    await page.click('#loginSubmitBtn');
    await page.waitForURL('**/dashboard');
    await expect(page.locator('#welcomeTitle')).toHaveText('Nadia Fotso');

    // 3. two parcels on GREEN Map: one online, one drawn offline
    await page.goto('/map');
    await drawParcel(page, [3.8500, 11.5000], 'Nord');
    await expect(page.locator('#pSync')).toHaveText(tr(lang, 'map.sync.synced'), { timeout: 15000 });
    await page.locator('[data-back="list"]').click();
    await context.setOffline(true);
    await drawParcel(page, [3.8530, 11.5030], 'Sud');
    await expect(page.locator('#pSync')).toHaveText(tr(lang, 'map.sync.pending'));
    await context.setOffline(false);
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    await expect(page.locator('#pSync')).toHaveText(tr(lang, 'map.sync.synced'), { timeout: 15000 });

    // 4. grid + mission on the first parcel
    await page.locator('[data-back="list"]').click();
    await page.locator('.parcel-item', { hasText: 'Nord' }).click();
    await page.click('#gridBtn');
    await page.locator('#cellSize').fill('10');
    await page.click('#previewBtn');
    await expect(page.locator('#gridSummary')).not.toBeEmpty();
    await page.click('#createMissionBtn');
    await expect(page.locator('#viewMission')).toBeVisible();
    const missionHref = (await page.locator('#analyseMissionLink').getAttribute('href'))!;

    // 5. analyses: photos queued while offline, sent when back online, tagged with the mission cell
    await page.goto(missionHref);
    await expect(page.locator('#cellBox')).toBeVisible();
    await page.fill('#cellInput', '1');
    await page.click('#tabPhotos');
    await context.setOffline(true);
    await page.setInputFiles('#uploadInput', [
      { name: 'a.png', mimeType: 'image/png', buffer: png('#2a8a3a') },
      { name: 'b.png', mimeType: 'image/png', buffer: png('#c04030') },
    ]);
    await expect(page.locator('#queueStat')).toHaveText(tr(lang, 'camera.status.queue_value_other', { count: 2 }));
    await context.setOffline(false);
    await page.evaluate(() => window.dispatchEvent(new Event('online')));
    // Intl.PluralRules: 0 is "one" in French, "other" in English
    const zero = tr(lang, `camera.status.queue_value_${lang === 'fr' ? 'one' : 'other'}`, { count: 0 });
    await expect(page.locator('#queueStat')).toHaveText(zero, { timeout: 20000 });
    await expect(page.locator('#resultBody .fiche-disclaimer')).toBeVisible();

    // 6. history -> field sheet
    await page.goto('/history');
    await page.locator('#histBody tr').first().click();
    await expect(page.locator('#ficheContent .fiche-disclaimer')).toBeVisible();
    await expect(page.locator('#ficheContent img.fiche-img')).toBeVisible();

    // 7. heatmap of the mission: cell 1 analysed
    await page.goto('/map');
    await page.locator('.parcel-item', { hasText: 'Nord' }).click();
    await page.locator('[data-mission]').first().click();
    await expect(page.locator('#viewMission')).toBeVisible();
    await page.waitForFunction('S.mission && S.heat');
    const total = await page.evaluate('S.mission.cells_total') as number;
    await expect(page.locator('#mProgress')).toHaveText(tr(lang, 'map.mission.progress', { done: 1, total }));
    await expect(page.locator('#legend')).toBeVisible();

    // 8. GreenBot opened from the field sheet keeps the analysis context
    await page.goto('/history');
    await page.locator('#histBody tr').first().click();
    const bot = page.locator('#ficheContent a.fiche-bot');
    if (await bot.count()) {
      await bot.click();
      await page.waitForURL('**/chatbot?analysis_id=*');
      await expect(page.locator('#ctxBar')).toBeVisible();
    }

    // 9. GREEN Data as a partner, CSV export
    setRole(`+237${phone}`, 'partner');
    await page.goto('/green-data');
    await expect(page.locator('.nav-item[data-page="green-data"]')).toHaveCount(1, { timeout: 10000 });
    await expect(page.locator('#mKanon')).toHaveText(tr(lang, 'green_data.method.kanon', { k: 5 }));
    const [download] = await Promise.all([page.waitForEvent('download'), page.click('#csvBtn')]);
    const csv = fs.readFileSync(await download.path(), 'utf8');
    expect(csv.split('\n')[0].trim()).toBe('region,month,plant,result,analyses');

    // 10. sign out
    await page.goto('/settings');
    await page.locator('button', { hasText: tr(lang, 'common.actions.sign_out') }).click();
    await page.waitForURL((u) => u.pathname === '/');
    expect(await page.evaluate(() => localStorage.getItem('green_token'))).toBeNull();
  });
}
