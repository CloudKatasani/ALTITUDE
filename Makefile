PY ?= .venv/bin/python
ALT ?= .venv/bin/altitude

.PHONY: install check test lint generate demo demo-serve

install:
	python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'

lint:
	$(ALT) knowledge validate
	$(PY) tools/lint_thresholds.py
	$(PY) tools/lint_branding.py
	$(ALT) generate --check

test:
	$(PY) -m pytest

check: lint test

generate:
	$(ALT) generate

demo:
	$(PY) tools/demo.py out/demo

demo-serve:
	$(PY) tools/demo.py out/demo --keep-running
