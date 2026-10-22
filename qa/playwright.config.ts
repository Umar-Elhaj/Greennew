import { defineConfig, devices } from '@playwright/test';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

// A throw-away SQLite database and MEDIA_DIR per run: e2e never touches
// a developer's database (real env vars win over the repo's .env).
// Created once by the main process; workers re-load this file and must reuse it.
const RUN_DIR = process.env.E2E_RUN_DIR || fs.mkdtempSync(path.join(os.tmpdir(), 'green-e2e-'));
process.env.E2E_RUN_DIR = RUN_DIR;
const PORT = Number(process.env.E2E_PORT || 8765);
const ROOT = path.resolve(__dirname, '..');
// Shared with the specs (workers inherit the environment): lets a test give
// a role with scripts/set_role.py or seed demo data on the e2e database.
process.env.E2E_DATABASE_URL = `sqlite:///${path.join(RUN_DIR, 'e2e.db')}`;
process.env.E2E_ROOT = ROOT;

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.ts/,
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'report' }]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    ...devices['Desktop Chrome'],
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `${ROOT}/.venv/bin/uvicorn main:app --port ${PORT} --host 127.0.0.1`,
    cwd: path.join(ROOT, 'backend'),
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      DEBUG: 'true',
      SECRET_KEY: 'e2e-secret-key',
      DATABASE_URL: `sqlite:///${path.join(RUN_DIR, 'e2e.db')}`,
      MEDIA_DIR: path.join(RUN_DIR, 'media'),
      E2E_FAKE_MODEL: '1',
      GEMINI_API_KEY: '',
      WEATHER_API_KEY: '',
    },
  },
});
