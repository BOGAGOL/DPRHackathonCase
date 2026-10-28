// Real Chrome + real HTTPS. Credentials enter only on stdin; stdout is booleans.
// Run from the repository with app/web's reviewed Playwright dependencies installed.
import { createRequire } from 'node:module';
const require = createRequire(new URL('../../app/web/package.json', import.meta.url));
const { chromium } = require('playwright');
let input = '';
for await (const chunk of process.stdin) input += chunk;
let browser;
const checks = {}, coverage = {};
function check(name, condition) { checks[name] = Boolean(condition); }
const forbidden = new Set(['password_hash','token_hash','csrf_hash','dek_pii_wrapped','dek_fin_wrapped']);
function noInternalValues(value) {
  return !value || typeof value !== 'object' || Object.entries(value).every(([k,v]) =>
    !forbidden.has(k) && !k.endsWith('_ct') && !k.endsWith('_bidx') && noInternalValues(v));
}
try {
  const config = JSON.parse(input); input = '';
  const origin = new URL(config.baseURL);
  if (origin.protocol !== 'https:' || origin.pathname !== '/') throw new Error('HTTPS origin required');
  const args = [];
  if (config.spki) {
    if (!['localhost','127.0.0.1'].includes(origin.hostname) || !/^[A-Za-z0-9+/]+={0,2}$/.test(config.spki)) throw new Error('Local certificate pin only');
    args.push(`--ignore-certificate-errors-spki-list=${config.spki}`);
  }
  coverage.stage = 'launch';
  browser = await chromium.launch({ channel: 'chrome', headless: true, args });
  const roles = ['privileged_officer','operator','finance_officer','anggota','analyst','auditor'];
  if (roles.some(role => !config.accounts[role]?.username || !config.accounts[role]?.password)) throw new Error('Six accounts required');
  let knownId, otherId = config.otherRecordId, fullName, fullKtp;
  for (const role of roles) {
    coverage.stage = `role:${role}`;
    const context = await browser.newContext({ baseURL:origin.origin, ignoreHTTPSErrors:false });
    try {
      const page = await context.newPage();
      const response = await page.goto('/login');
      check(`${role}:https_login_page`, response?.status() === 200);
      const csp = response?.headers()['content-security-policy'] || '';
      check(`${role}:strict_csp`, csp.includes("'nonce-") && csp.includes("frame-ancestors 'none'") && !csp.includes('unsafe-inline') && !csp.includes('unsafe-eval'));
      const account = config.accounts[role];
      await page.locator('#username').fill(account.username);
      await page.locator('#password').fill(account.password);
      await page.getByRole('button',{name:'Masuk ke aplikasi',exact:true}).click();
      await page.waitForURL(url => ['/anggota','/analytics','/audit'].includes(url.pathname),{timeout:25000});
      const me = await page.request.get('/api/auth/me');
      check(`${role}:login_identity`, me.status() === 200 && (await me.json()).role === role);
      const session = (await context.cookies()).find(c => c.name === 'dpr_session');
      check(`${role}:secure_session_cookie`, session?.httpOnly && session?.secure && session?.sameSite === 'Strict');
      check(`${role}:empty_browser_storage`, await page.evaluate(() => localStorage.length === 0 && sessionStorage.length === 0));
      const listing = await page.request.get('/api/anggota?page=1');
      if (['analyst','auditor'].includes(role)) {
        check(`${role}:member_list_denied`, listing.status() === 403);
        check(`${role}:member_detail_denied`, (await page.request.get(`/api/anggota/${knownId || '1'}`)).status() === 403);
      } else {
        check(`${role}:member_list_allowed`, listing.status() === 200);
        if (listing.status() === 200) {
          const list = await listing.json();
          check(`${role}:list_allowlist`, list.items.every(row => Object.keys(row).every(k => ['anggota_id','nama'].includes(k))));
          check(`${role}:no_internal_values`, noInternalValues(list));
          const first = list.items[0];
          check(`${role}:assigned_record_available`, Boolean(first));
          if (first) {
            if (role === 'privileged_officer') { knownId=first.anggota_id; otherId ||= list.items[1]?.anggota_id; }
            const detail = await page.request.get(`/api/anggota/${first.anggota_id}`);
            check(`${role}:assigned_detail_allowed`, detail.status() === 200);
            if (detail.status() === 200) {
              const body = await detail.json();
              check(`${role}:detail_no_internal_values`, noInternalValues(body));
              check(`${role}:finance_field_boundary`, ['rekening','nama_rekening','npwp','kode_bank'].every(k => (k in body) === (role === 'finance_officer')));
              if (role === 'privileged_officer') { fullName=body.nama; fullKtp=body.no_ktp; }
              if (['operator','finance_officer'].includes(role)) {
                check(`${role}:list_name_masked`, typeof first.nama === 'string' && first.nama.includes('*'));
                check(`${role}:nik_masked`, body.no_ktp == null || (body.no_ktp.includes('*') && (first.anggota_id !== knownId || body.no_ktp !== fullKtp)));
                check(`${role}:religion_absent`, !('agama' in body));
              }
              if (role === 'anggota') {
                check('anggota:one_own_record', list.total === 1 && list.items.length === 1);
                const foreign = [knownId,otherId].find(id => id && id !== first.anggota_id);
                coverage.foreign_record_idor = Boolean(foreign);
                if (foreign) check('anggota:foreign_record_denied', (await page.request.get(`/api/anggota/${foreign}`)).status() === 404);
              }
            }
          }
        }
      }
      const analytics = await page.request.get('/api/analytics/summary');
      check(`${role}:analytics_role_boundary`, analytics.status() === (role === 'analyst' ? 200 : 403));
      if (role === 'analyst' && analytics.status() === 200) {
        const body = await analytics.json();
        check('analyst:total_unavailable', body.total === null);
        check('analyst:only_released_marginals', body.groups.every(g => ['jenis_kelamin','pekerjaan_terakhir','nama_kppn','nama_bank','age_band'].includes(g.dimension) && Number.isInteger(g.count) && g.count >= 5 && Object.keys(g).every(k => ['dimension','value','count'].includes(k))));
        check('analyst:released_groups_present', body.groups.length > 0);
        check('analyst:cohort_filter_rejected', (await page.request.get('/api/analytics/summary?nama_kppn=synthetic')).status() === 422);
        if (config.smallLabel) check('analyst:known_small_label_absent', !body.groups.some(g => g.value === config.smallLabel));
        const filtered = await page.request.get('/api/analytics/summary?dimension=age_band');
        check('analyst:released_dimension_filter', filtered.status() === 200 && (await filtered.json()).groups.every(g => g.dimension === 'age_band'));
      }
      const audit = await page.request.get('/api/audit?page=1');
      check(`${role}:audit_role_boundary`, audit.status() === (role === 'auditor' ? 200 : 403));
      if (role === 'auditor' && audit.status() === 200) {
        const body = await audit.json();
        const allowed = new Set(['id','actor','role','action','anggota_id','field_class','decision','request_id','created_at']);
        check('auditor:metadata_allowlist', body.items.every(row => Object.keys(row).every(k => allowed.has(k))) && noInternalValues(body));
      }
      check(`${role}:api_no_store`, me.headers()['cache-control']?.includes('no-store'));
      await page.getByRole('button',{name:'Keluar',exact:true}).click();
      await page.waitForURL('**/login');
      check(`${role}:logout_revokes_session`, (await page.request.get('/api/auth/me')).status() === 401);
    } finally { await context.close(); }
  }
  coverage.stage = 'complete';coverage.real_chrome = true; coverage.network_mocking = false; coverage.application_data_mutations = false;
  console.log(JSON.stringify({status:Object.values(checks).every(Boolean)?'PASSED':'FAILED',checks,coverage}));
  if (!Object.values(checks).every(Boolean)) process.exitCode=1;
} catch (error) {
  console.log(JSON.stringify({status:'FAILED',checks,coverage,error_type:error?.constructor?.name || 'Error'}));
  process.exitCode=1;
} finally { if (browser) await browser.close(); }
