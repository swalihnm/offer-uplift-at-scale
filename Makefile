PY ?= .venv/bin/python
export PYTHONPATH := src

.PHONY: data lake ab uplift roi bq export all test

data lake:
	$(PY) -m oua.lake

ab:
	$(PY) -m oua.ab_test

uplift:
	$(PY) -m oua.uplift

roi:
	$(PY) -m oua.roi

bq:
	$(PY) -m oua.bq_load

export:
	$(PY) -m oua.export

all: lake ab uplift roi bq export

test:
	$(PY) -m pytest -q
