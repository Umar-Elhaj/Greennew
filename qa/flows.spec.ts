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
