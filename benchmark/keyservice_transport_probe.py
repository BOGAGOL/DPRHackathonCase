"""Paired bounded HTTP transport microprobe; no database or stored key changes."""

import os
import ssl

import httpx

from dprcrypto import OpenBaoClient
from dprcrypto.https_pool import VerifiedHTTPSPool
from .common import ROOT, utc_now, write_json
from .keyservice_diagnose import measure


def run():
    report = {'started_at_utc': utc_now(), 'calls_per_case': 200,
              'kind': 'bounded_verified_https_transport_probe', 'cases': []}
    previous = os.environ.get('DPR_OPENBAO_HTTP_TRANSPORT')
    try:
        for kind in ('httpx', 'https_pool'):
            os.environ['DPR_OPENBAO_HTTP_TRANSPORT'] = kind
            for concurrency in (1, 8):
                clients = []
                try:
                    for _ in range(concurrency):
                        client = OpenBaoClient()
                        clients.append(client)
                        client.hmac(b'bidx|v1|no_ktp|00000000000001')
                    functions = [lambda i, c=c: c.hmac(b'bidx|v1|no_ktp|00000000000001') for c in clients]
                    result = {'transport': kind, 'concurrency': concurrency, **measure(functions, 200)}
                    result['pools'] = [c._transport.stats() for c in clients if hasattr(c._transport, 'stats')]
                    report['cases'].append(result)
                    print({k: v for k, v in result.items() if k != 'pools'}, flush=True)
                finally:
                    for client in clients:
                        client.close()
    finally:
        if previous is None:
            os.environ.pop('DPR_OPENBAO_HTTP_TRANSPORT', None)
        else:
            os.environ['DPR_OPENBAO_HTTP_TRANSPORT'] = previous
        report['completed_at_utc'] = utc_now()
        untrusted = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        untrusted.minimum_version = ssl.TLSVersion.TLSv1_2
        pool = VerifiedHTTPSPool(os.environ['OPENBAO_ADDR'], untrusted)
        try:
            pool.request_bytes('GET', '/v1/sys/seal-status', None, {})
            report['untrusted_ca_rejected'] = False
        except httpx.HTTPError:
            report['untrusted_ca_rejected'] = True
        finally:
            pool.close()
        write_json(ROOT / 'evidence/benchmark/keyservice_latency/transport_pool_probe.json', report)
    return report


if __name__ == '__main__':
    run()
