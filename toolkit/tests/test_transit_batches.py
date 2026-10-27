import base64
import json
import os

import httpx
import pytest

from dprcrypto import CryptoError, OpenBaoClient, OpenBaoError


@pytest.mark.parametrize("operation",["wrap","hmac"])
@pytest.mark.parametrize("failure",[None,"partial","reordered","short","missing","version","encoding"])
def test_batch_responses_are_atomic_bounded_and_ordered(bao,operation,failure,caplog):
    def handler(request):
        if request.url.path.endswith("lookup-self"):return bao.handler(request)
        payload=json.loads(request.content)
        results=[]
        for item in payload["batch_input"]:
            output={"reference":item["reference"]}
            key="ciphertext" if operation=="wrap" else "hmac"
            output[key]="vault:v1:"+base64.b64encode(os.urandom(60 if operation=="wrap" else 32)).decode()
            results.append(output)
        if failure=="partial":results[-1]["error"]="withheld"
        elif failure=="reordered":results.reverse()
        elif failure=="short":results.pop()
        elif failure=="missing":results[-1].pop("ciphertext" if operation=="wrap" else "hmac")
        elif failure=="version":results[-1]["ciphertext" if operation=="wrap" else "hmac"]="vault:v0:invalid"
        elif failure=="encoding":results[-1]["ciphertext" if operation=="wrap" else "hmac"]="vault:v1:not-base64"
        return httpx.Response(200,json={"data":{"batch_results":results}})
    with OpenBaoClient(transport=httpx.MockTransport(handler),clock=lambda:bao.now) as client:
        client.require_policy("svc-app")
        with pytest.raises(OpenBaoError):client.require_policy("svc-migration")
        with pytest.raises(OpenBaoError):client.require_policy("root")
        call=(lambda values:client.wrap_batch("pii-kek",values)) if operation=="wrap" else client.hmac_batch
        if failure:
            with pytest.raises(OpenBaoError):call([os.urandom(32),os.urandom(32)])
        else:
            assert len(call([os.urandom(32),os.urandom(32)]))==2
            assert call([])==[]
        with pytest.raises(CryptoError):call([os.urandom(32)]*101)
        assert all(token not in caplog.text for token in bao.tokens.values())


def test_invalid_batch_inputs_fail_before_request(bao):
    for deks in (None,[os.urandom(31)]):
        with pytest.raises((CryptoError,OpenBaoError)):bao.client.wrap_batch("pii-kek",deks)
    with pytest.raises(CryptoError):bao.client.wrap_batch("unknown",[])
    for messages,version in ((None,1),(["text"],1),([],0),([],True)):
        with pytest.raises(CryptoError):bao.client.hmac_batch(messages,key_version=version)
    with pytest.raises(CryptoError):bao.client._batch_results("unused",[{}]*101)
