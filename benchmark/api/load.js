import http from 'k6/http';
import execution from 'k6/execution';
import { Trend } from 'k6/metrics';

const base = 'https://127.0.0.1:8100';
const keys = JSON.parse(open(__ENV.API_KEYS_FILE));
const account = JSON.parse(open(__ENV.API_ACCOUNT_FILE)).find(a => a.role === 'privileged_officer');
const latency = new Trend('api_latency_ms');
const warmupMs = Number(__ENV.API_WARMUP_SECONDS || '0') * 1000;
const endpoint = __ENV.API_ENDPOINT;
let measuredIndex = 0;
let warmupIndex = 0;

export const options = {
  scenarios: { read: { executor: 'constant-vus', vus: 8, duration: `${60 + warmupMs / 1000}s`, gracefulStop: '15s' } },
  setupTimeout: '60s', insecureSkipTLSVerify: false, noConnectionReuse: false,
  systemTags: ['status', 'method', 'name', 'scenario'], discardResponseBodies: true,
};

export function setup() {
  const sessions = [];
  for (let i = 0; i < 8; i++) {
    http.cookieJar().clear(base);
    const csrf = http.get(base + '/auth/csrf', { tags: { name: 'auth_csrf' } });
    if (csrf.status !== 200 || !csrf.cookies.dpr_csrf) throw new Error('csrf_failed');
    const token = csrf.cookies.dpr_csrf[0].value;
    const login = http.post(base + '/auth/login', JSON.stringify({ username: account.username, password: account.password }), {
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token, Origin: base },
      cookies: { dpr_csrf: token }, tags: { name: 'auth_login' },
    });
    if (login.status !== 200 || !login.cookies.dpr_session) throw new Error('login_failed_status_' + login.status);
    sessions.push({ dpr_session: login.cookies.dpr_session[0].value, dpr_csrf: login.cookies.dpr_csrf[0].value });
  }
  return { sessions };
}

export default function (data) {
  const measuring = Date.now() - execution.scenario.startTime >= warmupMs;
  const index = (measuring ? measuredIndex++ : warmupIndex++) * 8 + (__VU - 1);
  const key = keys.profiles[index % keys.profiles.length];
  let path;
  if (endpoint === 'api_list_page') path = '/anggota?page=' + keys.pages[index % keys.pages.length];
  else if (endpoint === 'api_read_profile') path = '/anggota/' + key.id;
  else if (endpoint === 'api_search_nik') path = '/anggota/search?no_ktp=' + encodeURIComponent(key.no_ktp);
  else if (endpoint === 'api_search_email') path = '/anggota/search?email=' + encodeURIComponent(key.email);
  else throw new Error('endpoint_not_authorized');
  const response = http.get(base + path, { cookies: data.sessions[(__VU - 1) % 8], timeout: '10s', tags: { name: endpoint } });
  if (measuring) {
    // Blocked includes connection acquisition; duration ends after the full response.
    latency.add(response.timings.blocked + response.timings.duration, {
      endpoint, status: String(response.status), ok: response.status === 200 && !response.error_code ? '1' : '0',
      error_code: String(response.error_code || 0),
    });
  }
}

export function handleSummary() { return {}; }
