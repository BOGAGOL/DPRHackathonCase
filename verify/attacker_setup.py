"""Operator-only issuance of isolated simulation identities; never root in leak workers."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
from uuid import uuid4

from infra.openbao.api import BaoError, from_environment
from infra.openbao.init import save_response
from infra.security import external_directory, secure_directory


def policy_documents():
    common = 'path "auth/token/lookup-self" { capabilities = ["read"] }\npath "auth/token/revoke-self" { capabilities = ["update"] }\n'
    return {
        "modc-leak-pii": common + 'path "transit/decrypt/pii-kek" { capabilities = ["update"] }\n',
        "modc-leak-finance": common + 'path "transit/decrypt/finance-kek" { capabilities = ["update"] }\n',
        "modc-leak-search": common + 'path "transit/hmac/search-hmac" { capabilities = ["update"] }\npath "transit/hmac/search-hmac/sha2-256" { capabilities = ["update"] }\n',
    }


def configure_and_issue(api, root, operator_token):
    identity = api.request("/auth/token/lookup-self", token=operator_token)["data"]
    if identity["policies"] != ["root"]:
        raise ValueError("Expected isolated operator bootstrap identity")
    directory = secure_directory(external_directory(str(root)) / "openbao/tokens")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    result = []
    for policy, text in policy_documents().items():
        try:
            current = api.request("/sys/policies/acl/" + policy, token=operator_token)["data"]["policy"]
            if "".join(current.split()) != "".join(text.split()):
                raise ValueError("Existing simulation policy differs; do not overwrite")
        except BaoError as error:
            if error.status != 404:
                raise
            api.request("/sys/policies/acl/" + policy, {"policy": text}, token=operator_token)
        destination = directory / (policy + "-" + stamp + ".json")
        save_response(destination, lambda policy=policy: api.request("/auth/token/create-orphan",
            {"policies": [policy], "no_default_policy": True, "renewable": False, "ttl": "14400s",
             "explicit_max_ttl": "14400s", "display_name": policy}, token=operator_token))
        result.append({"policy": policy, "filename": destination.name, "ttl_seconds": 14400})
    return result


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    root = Path(os.environ["DPR_SECRETS_DIR"])
    configure_and_issue(from_environment(), root, os.environ["OPENBAO_TOKEN"])
    print("Three restricted simulation tokens saved outside repo; TTL 4h; values withheld.")


if __name__ == "__main__":
    main()
