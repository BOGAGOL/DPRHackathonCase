"""TLS-verified correctness client. Never serialize bodies or request URLs to evidence."""
import ssl
import httpx

BASE = 'https://127.0.0.1:8100'
ENDPOINTS = ('api_list_page', 'api_read_profile', 'api_search_nik', 'api_search_email')


def client(ca):
    return httpx.Client(base_url=BASE, verify=ssl.create_default_context(cafile=str(ca)),
                        http2=False, trust_env=False, follow_redirects=False, timeout=15)


def login(session, account):
    result = session.get('/auth/csrf')
    if result.status_code != 200:
        raise RuntimeError('csrf_failed')
    token = session.cookies.get('dpr_csrf')
    result = session.post('/auth/login', json={'username': account['username'], 'password': account['password']},
                          headers={'X-CSRF-Token': token, 'Origin': BASE})
    if result.status_code != 200:
        raise RuntimeError('login_failed_status_' + str(result.status_code))


def request(session, endpoint, key, page):
    if endpoint == 'api_list_page':
        return session.get('/anggota', params={'page': page})
    if endpoint == 'api_read_profile':
        return session.get('/anggota/' + str(key['id']))
    if endpoint == 'api_search_nik':
        return session.get('/anggota/search', params={'no_ktp': key['no_ktp']})
    if endpoint == 'api_search_email':
        return session.get('/anggota/search', params={'email': key['email']})
    raise ValueError('unauthorized_endpoint')


def mismatched_fields(before, after, path=''):
    if isinstance(before, dict) and isinstance(after, dict):
        return [p for key in sorted(before.keys() | after.keys()) for p in
                ([path + key] if key not in before or key not in after else mismatched_fields(before[key], after[key], path + key + '.'))]
    if isinstance(before, list) and isinstance(after, list):
        if len(before) != len(after):
            return [path + 'length']
        return [p for i, (b, a) in enumerate(zip(before, after)) for p in mismatched_fields(b, a, path + str(i) + '.')]
    return [] if before == after else [path.rstrip('.')]
