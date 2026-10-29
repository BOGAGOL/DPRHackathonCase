PYTHON ?= python
LABEL ?= before
SCANNER_OUT = results/scanner/$(LABEL)

# Cross-platform launcher; DATA is optional when DPR_DEMO_DATA is injected.
DATA_ARG = $(if $(DATA),--data "$(DATA)",)
.PHONY: setup demo verify test
setup:
	$(PYTHON) -m infra.reproduce setup

demo:
	$(PYTHON) -m infra.reproduce demo $(DATA_ARG)

verify:
	$(PYTHON) -m infra.reproduce verify $(DATA_ARG)

test:
	$(PYTHON) -m infra.reproduce test

.PHONY: results
results:
	$(PYTHON) -m infra.reproduce results

.PHONY: scanner-install scan scan-dump scan-eval scanner-test
scanner-install:
	$(PYTHON) -m pip install -r scanner/requirements.txt

scan:
	$(PYTHON) -m scanner db --schema public --sample 1000 --label "$(LABEL)" --out "$(SCANNER_OUT)"

scan-dump:
	$(PYTHON) -m scanner dump --file "$(FILE)" --label "$(LABEL)" --out "$(SCANNER_OUT)"

scan-eval:
	$(PYTHON) -m scanner evaluate --pred "$(SCANNER_OUT)/inventory.csv" --truth scanner/ground_truth_eval.csv --out "$(SCANNER_OUT)/evaluation.json"

scanner-test:
	$(PYTHON) -m pytest scanner/tests -q

# Optional shortcuts; equivalent python -m commands work in PowerShell.
.PHONY: test-core test-service
test-core:
	$(PYTHON) -m pytest -q

test-service:
	$(PYTHON) -m pytest -c app/pytest.ini app/tests -q

.PHONY: source-check source-sbom source-build
source-check:
	$(PYTHON) -m infra.distribution check

source-sbom:
	$(PYTHON) -m infra.distribution sbom

source-build:
	$(PYTHON) -m infra.distribution build --output dist/source
