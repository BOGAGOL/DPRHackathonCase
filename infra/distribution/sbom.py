"""CycloneDX 1.6 inventories with explicit declared/lockfile completeness limits."""

import base64
import hashlib
import json
import re
import tomllib
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

from packaging.requirements import Requirement
import yaml

from .inventory import text_sha


def inputs(root):
    names = [
        f"{module}/requirements.txt"
        for module in (
            "app",
            "infra",
            "scanner",
            "datagen",
            "benchmark",
            "verify",
            "infra/distribution",
        )
    ]
    names += [
        "toolkit/pyproject.toml",
        "app/web/package-lock.json",
        "infra/compose.yaml",
        "infra/vm/compose.yaml",
        "infra/reproduce/compose.yaml",
        "infra/tests/compose.postgres.yaml",
    ]
    return {name: text_sha(root / name) for name in names if (root / name).is_file()}


def document(name, components, fingerprints, completeness):
    identity = hashlib.sha256(
        json.dumps([name, fingerprints, components], sort_keys=True).encode()
    ).hexdigest()
    return {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:"
        + str(uuid5(NAMESPACE_URL, "dpr-submission:" + identity)),
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": "dpr-project",
                "name": "DPR Data Protection Prototype",
                "version": "contract-v1",
            },
            "properties": [
                {"name": "dpr:inventory-scope", "value": completeness},
                {
                    "name": "dpr:input-sha256-lf",
                    "value": json.dumps(fingerprints, sort_keys=True),
                },
            ],
        },
        "components": components,
    }


def python_components(root):
    declarations = []
    for name in inputs(root):
        if not name.endswith("requirements.txt"):
            continue
        for line in (root / name).read_text().splitlines():
            value = line.split(" #", 1)[0].strip()
            if value and not value.startswith("#"):
                declarations.append((name, value))
    project = tomllib.loads((root / "toolkit/pyproject.toml").read_text())
    for value in project["project"]["dependencies"]:
        declarations.append(("toolkit/pyproject.toml:runtime", value))
    for value in project["build-system"]["requires"]:
        declarations.append(("toolkit/pyproject.toml:build", value))
    for group, requirements in (
        project["project"].get("optional-dependencies", {}).items()
    ):
        for value in requirements:
            declarations.append(("toolkit/pyproject.toml:" + group, value))
    grouped = {}
    for source, value in declarations:
        requirement = Requirement(value)
        normalized = re.sub(r"[-_.]+", "-", requirement.name).lower()
        key = (
            normalized,
            str(requirement.specifier),
            tuple(sorted(requirement.extras)),
            str(requirement.marker or ""),
        )
        grouped.setdefault(key, []).append(source)
    components = []
    for (name, constraint, extras, marker), sources in sorted(grouped.items()):
        exact = re.fullmatch(r"==([^*,]+)", constraint)
        version = exact.group(1) if exact else None
        ref = (
            "python:"
            + hashlib.sha256(
                json.dumps([name, constraint, extras, marker]).encode()
            ).hexdigest()[:20]
        )
        item = {
            "type": "library",
            "bom-ref": ref,
            "name": name,
            "purl": "pkg:pypi/"
            + name
            + ("@" + quote(version, safe="") if version else ""),
            "properties": [
                {"name": "dpr:constraint", "value": constraint},
                {"name": "dpr:extras", "value": ",".join(extras)},
                {"name": "dpr:environment-marker", "value": marker},
                {"name": "dpr:declared-in", "value": ";".join(sorted(set(sources)))},
                {
                    "name": "dpr:resolution",
                    "value": "declared-pin" if version else "unresolved-range",
                },
            ],
        }
        if version:
            item["version"] = version
        components.append(item)
    return components


def node_components(root):
    lock = json.loads((root / "app/web/package-lock.json").read_text())
    if lock.get("lockfileVersion") != 3:
        raise ValueError("Reviewed npm lockfile v3 required")
    components = []
    for path, package in sorted(lock["packages"].items()):
        if not path:
            continue
        name = package.get("name") or path.rsplit("node_modules/", 1)[-1]
        item = {
            "type": "library",
            "bom-ref": "npm:" + path,
            "name": name,
            "version": package["version"],
            "purl": "pkg:npm/"
            + quote(name, safe="/")
            + "@"
            + quote(package["version"], safe=""),
            "properties": [
                {"name": "dpr:lock-path", "value": path},
                {
                    "name": "dpr:development",
                    "value": str(bool(package.get("dev"))).lower(),
                },
            ],
        }
        if package.get("license"):
            item["licenses"] = [{"license": {"name": package["license"]}}]
        integrity = package.get("integrity", "").split(" ")[0]
        match = re.fullmatch(r"(sha256|sha384|sha512)-(.+)", integrity)
        if match:
            item["hashes"] = [
                {
                    "alg": {
                        "sha256": "SHA-256",
                        "sha384": "SHA-384",
                        "sha512": "SHA-512",
                    }[match[1]],
                    "content": base64.b64decode(match[2], validate=True).hex(),
                }
            ]
        components.append(item)
    return components


def infrastructure_components(root):
    images = {}
    for name in inputs(root):
        if not name.endswith(".yaml"):
            continue
        compose = yaml.safe_load((root / name).read_text())
        for service, config in compose["services"].items():
            if "image" in config:
                images.setdefault(config["image"], []).append(name + ":" + service)
    return [
        {
            "type": "container",
            "bom-ref": "image:" + image,
            "name": image.rsplit(":", 1)[0],
            "version": image.rsplit(":", 1)[1],
            "properties": [
                {"name": "dpr:image-reference", "value": image},
                {"name": "dpr:declared-in", "value": ";".join(sources)},
                {"name": "dpr:resolved-image-digest", "value": "NOT_CAPTURED"},
            ],
        }
        for image, sources in sorted(images.items())
    ]


def generate(root):
    fingerprints = inputs(root)
    definitions = {
        "python-declared.cdx.json": (
            python_components(root),
            "Declared direct/runtime/build/test requirements only; ranges remain unresolved; no transitive/deployed-environment completeness claim",
        ),
        "service-web-lock.cdx.json": (
            node_components(root),
            "All packages in the active frontend npm lockfile, including development/optional entries; integrity is declared by the lockfile, not independently fetched",
        ),
        "infrastructure.cdx.json": (
            infrastructure_components(root),
            "Compose image references; container OS packages and resolved image digests are not inventoried",
        ),
    }
    output = root / "docs/sbom"
    output.mkdir(parents=True, exist_ok=True)
    index = {
        "schema_version": 1,
        "format": "CycloneDX 1.6",
        "inputs_sha256_lf": fingerprints,
        "inventories": {},
    }
    for name, (components, scope) in definitions.items():
        (output / name).write_text(
            json.dumps(document(name, components, fingerprints, scope), indent=2)
            + "\n",
            encoding="utf-8",
        )
        index["inventories"][name] = {
            "components": len(components),
            "scope": scope,
            "sha256_lf": text_sha(output / name),
        }
    (output / "index.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8"
    )
    return index


def fresh(root):
    try:
        index = json.loads((root / "docs/sbom/index.json").read_text())
        expected = {
            "python-declared.cdx.json",
            "service-web-lock.cdx.json",
            "infrastructure.cdx.json",
        }
        return (
            index["inputs_sha256_lf"] == inputs(root)
            and set(index["inventories"]) == expected
            and all(
                text_sha(root / "docs/sbom" / name) == item["sha256_lf"]
                for name, item in index["inventories"].items()
            )
        )
    except (OSError, ValueError, KeyError):
        return False
