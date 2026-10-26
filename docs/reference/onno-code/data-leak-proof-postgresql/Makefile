SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

.PHONY: help check up down logs venv test openbao-init plaintext-scan package

help:
	@printf '%s\n' 'make check | up | down | logs | venv | test | openbao-init | plaintext-scan'

check:
	docker compose --env-file .env config --quiet
	python3 -m compileall -q toolkit benchmark
	bash -n scripts/*.sh benchmark/*.sh

up:
	docker compose --env-file .env up -d
	docker compose ps

down:
	docker compose down

logs:
	docker compose logs --tail=100

venv:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -r toolkit/requirements.txt

test:
	PYTHONPATH=toolkit .venv/bin/python -m pytest -q toolkit/tests

openbao-init:
	./scripts/init-openbao.sh

plaintext-scan:
	./scripts/plaintext-scan.sh

