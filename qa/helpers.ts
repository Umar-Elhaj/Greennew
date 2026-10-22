/** Shared helpers for the Playwright specs (not a spec file: importing it registers no test). */
import * as path from 'path';
import { execFileSync } from 'child_process';

/** Give a role to an account on the e2e database (scripts/set_role.py). */
export function setRole(phone: string, role: string) {
  execFileSync(path.join(process.env.E2E_ROOT!, '.venv', 'bin', 'python'),
    [path.join(process.env.E2E_ROOT!, 'scripts', 'set_role.py'), '--phone', phone, '--role', role],
    { env: { ...process.env, DATABASE_URL: process.env.E2E_DATABASE_URL } });
}
