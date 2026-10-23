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

test('camera: photos imported offline are queued, then sent when back online', async ({ page, context, request }) => {
  const s = await newUser(request);
  await signIn(page, s);
  await page.goto('/camera');
  await page.click('#tabPhotos');
  await context.setOffline(true);
  await page.setInputFiles('#uploadInput', [
    { name: 'a.png', mimeType: 'image/png', buffer: solidPng('#30a040') },
    { name: 'b.png', mimeType: 'image/png', buffer: solidPng('#a03040') },
  ]);
  await expect(page.locator('#queueStat')).toHaveText('2 images');
  await expect(page.locator('#netLabel')).toHaveText('Hors ligne');
  await expect(page.locator('.queue-item')).toHaveCount(2);
  // the queue survives a reload (IndexedDB) — reload needs the network, so check the DB instead
  const stored = await page.evaluate(() => UploadQueue.all().then((x: any[]) => x.length));
  expect(stored).toBe(2);
  await context.setOffline(false);
  await expect(page.locator('#queueStat')).toHaveText('0 image', { timeout: 20000 });
  await expect(page.locator('#resultBody')).toContainText('pas un diagnostic');
  const hist = await request.get('/api/analysis/history', { headers: { Authorization: `Bearer ${s.token}` } });
  expect((await hist.json()).total).toBe(2);
});

test('camera: photos queued by one account are neither shown to nor sent by another', async ({ browser, request }) => {
  const context = await browser.newContext();
  const a = await newUser(request);
  let page = await context.newPage();
  await signIn(page, a);
  await page.goto('/camera');
  await page.click('#tabPhotos');
  await context.setOffline(true);
  await page.setInputFiles('#uploadInput', [{ name: 'a.png', mimeType: 'image/png', buffer: solidPng('#30a040') }]);
  await expect(page.locator('.queue-item')).toHaveCount(1);
  await page.close();

  await context.setOffline(false);
  const b = await newUser(request);
  page = await context.newPage();
  await signIn(page, b);
  await page.goto('/camera');
  expect(await page.evaluate(() => UploadQueue.all().then((x: any[]) => x.length))).toBe(0);
  await expect(page.locator('.queue-item')).toHaveCount(0);
  const hist = await request.get('/api/analysis/history', { headers: { Authorization: `Bearer ${b.token}` } });
  expect((await hist.json()).total).toBe(0);
  await context.close();
});

test('camera: an invalid file is rejected and listed, then deletable', async ({ page, request }) => {
  const s = await newUser(request);
  await signIn(page, s);
  await page.goto('/camera');
  await page.click('#tabPhotos');
  await page.setInputFiles('#uploadInput', [{ name: 'fake.png', mimeType: 'image/png', buffer: Buffer.from('not an image') }]);
  await expect(page.locator('.qi-status.failed')).toHaveText('Refusée', { timeout: 15000 });
  await expect(page.locator('.qi-err')).toContainText("n'est pas une image valide");
  await page.locator('.queue-item button').click();
  await expect(page.locator('.queue-item')).toHaveCount(0);
});

test('GreenBot: explains when disabled, opens a conversation linked to an analysis', async ({ page, request }) => {
  const s = await newUser(request);
  const up = await upload(request, s.token, '#c04030');
  await signIn(page, s);
  await page.goto(`/chatbot?analysis_id=${up.analysis_id}`);
  await expect(page.locator('#notConfigured')).toBeVisible();   // no GEMINI_API_KEY in e2e
  await expect(page.locator('#ctxBar')).toBeVisible();
  await expect(page.locator('#ctxLabel')).toContainText('Brûlure des feuilles de la tomate');
  await expect(page.locator('#chatInput')).toBeDisabled();
  await page.locator('#appHeader .lang-switch-btn[data-lang="en"]').click();
  await expect(page.locator('#ctxLabel')).toContainText('Tomato leaf blight');
  await expect(page.locator('#notConfigured')).toContainText('not enabled');
});

test('economics: net ROI = (losses avoided - cost) / cost', async ({ page, request }) => {
  const s = await newUser(request);
  await signIn(page, s);
  await page.goto('/economics');
  // maize defaults: 2 ha, 2.5 t/ha, 175 XAF/kg, 25 % loss, 20 000 XAF/ha, 75 % effective
  await expect(page.locator('#roiValue')).toHaveText(/^310\s?%$/);
  await expect(page.locator('#kpiGross')).toContainText('875');
  await page.locator('#appHeader .lang-switch-btn[data-lang="en"]').click();
  await expect(page.locator('#scenarioRows')).toContainText('Epidemic, treated late');
});

/** Click a ring of points on the map, in pixels relative to the map container. */
async function clickRing(page: Page, points: Array<[number, number]>) {
  const box = await page.locator('#map').boundingBox();
  for (const [x, y] of points) await page.mouse.click(box!.x + x, box!.y + y);
}

test('GREEN Map: parcel drawn offline is kept, then synced when back online', async ({ page, context, request }) => {
  const s = await newUser(request);
  await signIn(page, s);
  await page.goto('/map');
  await page.evaluate('map.setView([3.85, 11.5], 18)');
  await context.setOffline(true);
  await expect(page.locator('#offlineBanner')).toBeVisible();

  await page.click('#newParcelBtn');
  await clickRing(page, [[200, 150], [420, 150], [420, 330], [200, 330]]);
  await expect(page.locator('#drawCount')).toHaveText('4 points');
  await expect(page.locator('#drawMsg')).toContainText('Surface');
  await page.click('#undoPointBtn');
  await expect(page.locator('#drawCount')).toHaveText('3 points');
  await clickRing(page, [[200, 330]]);
  await page.click('#finishDrawBtn');
  await page.fill('#fName', 'Champ hors ligne');
  await page.selectOption('#fCrop', 'Maize');
  await page.click('#saveParcelBtn');
  await expect(page.locator('#pSync')).toHaveText("En attente d'envoi");
  // nothing on the server yet
  let list = await (await request.get('/api/parcels', { headers: { Authorization: `Bearer ${s.token}` } })).json();
  expect(list.length).toBe(0);

  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(page.locator('#pSync')).toHaveText('Enregistrée', { timeout: 15000 });
  list = await (await request.get('/api/parcels', { headers: { Authorization: `Bearer ${s.token}` } })).json();
  expect(list.length).toBe(1);
  expect(list[0].name).toBe('Champ hors ligne');
  expect(list[0].area_ha).toBeGreaterThan(0.05);
  expect(list[0].region).toBe('Centre');
  await expect(page.locator('#pRegion')).toHaveText('Centre');
});

const SQUARE = { type: 'Polygon', coordinates: [[[11.5, 3.85], [11.5012, 3.85], [11.5012, 3.8512], [11.5, 3.8512], [11.5, 3.85]]] };

test('GREEN Map: two edits made offline are both sent, without a false conflict', async ({ page, context, request }) => {
  const s = await newUser(request);
  const auth = { Authorization: `Bearer ${s.token}` };
  const created = await (await request.post('/api/parcels', { headers: auth, data: { name: 'Avant', geometry: SQUARE } })).json();
  await signIn(page, s);
  await page.goto('/map');
  await page.locator('.parcel-item', { hasText: 'Avant' }).click();
  await context.setOffline(true);
  for (const name of ['Edition 1', 'Edition 2']) {
    await page.click('#editBtn');
    await page.fill('#fName', name);
    await page.click('#saveParcelBtn');
    await expect(page.locator('#pSync')).toHaveText("En attente d'envoi");
  }
  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(page.locator('#pSync')).toHaveText('Enregistrée', { timeout: 15000 });
  await expect(page.locator('#pConflict')).toBeHidden();
  const p = await (await request.get(`/api/parcels/${created.id}`, { headers: auth })).json();
  expect(p.name).toBe('Edition 2');
});

test('GREEN Map: an offline edit of a parcel changed elsewhere shows the conflict', async ({ page, context, request }) => {
  const s = await newUser(request);
  const auth = { Authorization: `Bearer ${s.token}` };
  const created = await (await request.post('/api/parcels', { headers: auth, data: { name: 'Avant', geometry: SQUARE } })).json();
  await signIn(page, s);
  await page.goto('/map');
  await page.locator('.parcel-item', { hasText: 'Avant' }).click();
  await context.setOffline(true);
  await page.click('#editBtn');
  await page.fill('#fName', 'Mon edition');
  await page.click('#saveParcelBtn');
  await page.waitForTimeout(1100);          // the server tolerates 1 s of clock skew
  await request.put(`/api/parcels/${created.id}`, { headers: auth, data: { name: 'Ailleurs' } });
  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(page.locator('#pSync')).toHaveText('Modifiée ailleurs', { timeout: 15000 });
  await expect(page.locator('#pConflict')).toBeVisible();
  await page.click('#applyDraftBtn');
  await expect(page.locator('#pSync')).toHaveText('Enregistrée', { timeout: 15000 });
  expect((await (await request.get(`/api/parcels/${created.id}`, { headers: auth })).json()).name).toBe('Mon edition');
});

test('GREEN Map: parcels kept offline on a shared device stay with their account', async ({ browser, request }) => {
  const context = await browser.newContext();
  const a = await newUser(request);
  let page = await context.newPage();
  await signIn(page, a);
  await page.goto('/map');
  await page.evaluate('map.setView([3.85, 11.5], 18)');
  await context.setOffline(true);
  await page.click('#newParcelBtn');
  await clickRing(page, [[200, 150], [420, 150], [420, 330], [200, 330]]);
  await page.click('#finishDrawBtn');
  await page.fill('#fName', 'Parcelle de A');
  await page.click('#saveParcelBtn');
  await expect(page.locator('#pSync')).toHaveText("En attente d'envoi");
  await page.close();

  await context.setOffline(false);
  const b = await newUser(request);
  page = await context.newPage();
  await signIn(page, b);
  await page.goto('/map');
  await expect(page.locator('#viewList')).toBeVisible();
  await page.evaluate('ParcelStore.sync()');
  expect(await page.evaluate('ParcelStore.list(false).then(l => l.map(p => p.name))')).toEqual([]);
  await expect(page.locator('#parcelList')).not.toContainText('Parcelle de A');
  const listB = await (await request.get('/api/parcels', { headers: { Authorization: `Bearer ${b.token}` } })).json();
  expect(listB.length).toBe(0);
  await context.close();
});

test('GREEN Map: self-crossing outline is refused while drawing', async ({ page, request }) => {
  const s = await newUser(request);
  await signIn(page, s);
  await page.goto('/map');
  await page.evaluate('map.setView([3.85, 11.5], 18)');
  await page.click('#newParcelBtn');
  await clickRing(page, [[200, 150], [420, 330], [420, 150], [200, 330]]);   // bow-tie
  await expect(page.locator('#drawMsg')).toHaveText('Le contour se croise : déplacez ou supprimez un point.');
  await expect(page.locator('#finishDrawBtn')).toBeDisabled();
});

test('GREEN Map: parcel -> grid -> mission -> 6 analyses -> heatmap', async ({ page, request }) => {
  const s = await newUser(request);
  const auth = { Authorization: `Bearer ${s.token}` };
  const lat0 = 3.85, lng0 = 11.5, mLat = 1 / 111195, mLng = 1 / (111195 * Math.cos(lat0 * Math.PI / 180));
  const ring = [[0, 0], [50, 0], [50, 20], [0, 20], [0, 0]].map(([x, y]) => [lng0 + x * mLng, lat0 + y * mLat]);
  const parcel = await (await request.post('/api/parcels', { headers: auth,
    data: { name: 'Grille', crop_type: 'Maize', geometry: { type: 'Polygon', coordinates: [ring] } } })).json();

  await signIn(page, s);
  await page.goto(`/map?parcel=${parcel.id}`);
  await expect(page.locator('#pName')).toHaveText('Grille');
  await page.click('#gridBtn');
  await page.locator('#cellSize').fill('5');
  await page.click('#previewBtn');
  await expect(page.locator('#gridSummary')).toContainText('40 cellules');
  await page.click('#createMissionBtn');
  await expect(page.locator('#viewMission')).toBeVisible();
  await expect(page.locator('#mProgress')).toHaveText('0 cellules analysées sur 40');
  const missionId = Number((await page.locator('#analyseMissionLink').getAttribute('href'))!.match(/mission_id=(\d+)/)![1]);

  const colors = ['#2a8a3a', '#8a6a2a', '#c04030', '#3060c0', '#a0a020', '#20a0a0'];
  const cells = [1, 1, 2, 2, 3, 5];
  for (let i = 0; i < 6; i++) {
    const r = await request.post('/api/camera/analyze-frame', { headers: auth, multipart: {
      file: { name: 'f.png', mimeType: 'image/png', buffer: solidPng(colors[i]) },
      mission_id: String(missionId), cell_index: String(cells[i]) } });
    expect(r.status(), await r.text()).toBe(200);
  }
  await page.reload();
  await page.goto(`/map?parcel=${parcel.id}&mission=${missionId}`);
  await expect(page.locator('#mProgress')).toHaveText('4 cellules analysées sur 40');
  await expect(page.locator('#legend')).toContainText('Non analysée');
  // 36 cells not analysed are hatched
  await expect(page.locator('#map path[fill="url(#green-hatch)"]')).toHaveCount(36);
  await page.selectOption('#heatIndicator', 'alert');
  await expect(page.locator('#legend')).toContainText("Niveau d'alerte le plus élevé");
  await page.locator('#map path[fill="url(#green-hatch)"]').first().waitFor();
  await page.screenshot({ path: 'screenshots/flows/map-heatmap.png' });
  // export of the waypoints for the rover
  const wp = await (await request.get(`/api/missions/${missionId}/waypoints`, { headers: auth })).json();
  expect(wp.waypoints.length).toBe(40);
});

test('camera: captures are tagged with the mission and the cell', async ({ page, request }) => {
  const s = await newUser(request);
  const auth = { Authorization: `Bearer ${s.token}` };
  const ring = [[11.5, 3.85], [11.5005, 3.85], [11.5005, 3.8502], [11.5, 3.8502], [11.5, 3.85]];
  const parcel = await (await request.post('/api/parcels', { headers: auth, data: { name: 'P', geometry: { type: 'Polygon', coordinates: [ring] } } })).json();
  const mission = await (await request.post('/api/missions', { headers: auth, data: { parcel_id: parcel.id, cell_size_m: 10 } })).json();
  await signIn(page, s);
  await page.goto(`/camera?parcel_id=${parcel.id}&mission_id=${mission.id}`);
  await expect(page.locator('#missionSelect')).toHaveValue(String(mission.id));
  await page.fill('#cellInput', '3');
  await page.click('#tabPhotos');
  await page.setInputFiles('#uploadInput', [{ name: 'a.png', mimeType: 'image/png', buffer: solidPng('#30a040') }]);
  await expect(page.locator('#resultBody')).toContainText('pas un diagnostic', { timeout: 15000 });
  const hm = await (await request.get(`/api/missions/${mission.id}/heatmap`, { headers: auth })).json();
  expect(hm.cells.map((c: any) => c.index)).toEqual([3]);
});

function runScript(args: string[]) {
  const { execFileSync } = require('child_process');
  const pathMod = require('path');
  return execFileSync(pathMod.join(process.env.E2E_ROOT!, '.venv', 'bin', 'python'),
    [pathMod.join(process.env.E2E_ROOT!, 'scripts', args[0]), ...args.slice(1)],
    { env: { ...process.env, DATABASE_URL: process.env.E2E_DATABASE_URL, DEBUG: 'true' } }).toString();
}

test('GREEN Data: farmers are refused, partners see aggregates (demo data, DEBUG only)', async ({ page, context, request }) => {
  const farmer = await newUser(request);
  await signIn(page, farmer);
  await page.goto('/green-data');
  await expect(page.locator('#forbidden')).toBeVisible();
  await expect(page.locator('.nav-item[data-page="green-data"]')).toHaveCount(0);

  runScript(['seed_demo.py', '--farmers-per-region', '5', '--analyses-per-farmer', '15']);
  const partner = await newUser(request);
  runScript(['set_role.py', '--phone', partner.phone, '--role', 'partner']);
  page = await context.newPage();      // the farmer's init script stays on the first page
  await signIn(page, partner);
  await page.goto('/green-data');
  await expect(page.locator('.nav-item[data-page="green-data"]')).toHaveCount(1);
  await expect(page.locator('#demoBox')).toBeVisible();
  await page.check('#fDemo');
  await page.click('#filters button[type="submit"]');
  await expect(page.locator('#mDemo')).toBeVisible();
  await expect(page.locator('#kpis')).toContainText('750');            // 10 regions x 5 farmers x 15 (>= 5 farmers: published)
  await expect(page.locator('#plantsBox canvas')).toBeVisible();
  await expect(page.locator('#matrixBox td.cell').first()).toBeVisible();
  await expect(page.locator('#regionMap path.leaflet-interactive')).toHaveCount(10);
  await page.selectOption('#fRegion', 'Littoral');
  await page.click('#filters button[type="submit"]');
  await expect(page.locator('#kpis')).toContainText('75');
  await page.screenshot({ path: 'screenshots/flows/green-data.png', fullPage: true });
  await page.locator('#appHeader .lang-switch-btn[data-lang="en"]').click();
  await expect(page.locator('.gd-method')).toContainText('Only analyses whose author agreed');
  runScript(['seed_demo.py', '--remove']);
});
