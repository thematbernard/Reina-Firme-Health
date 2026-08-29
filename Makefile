.PHONY: check extract load build

check:        ## connectivity smoke test against Redshift
	uv run pipeline/00_connect_check.py

profile:      ## dump schema + date ranges to docs/data-notes.md
	uv run pipeline/01_profile.py

extract:      ## pull Redshift tables to data/raw/*.parquet (skips existing)
	uv run pipeline/02_extract.py

load:         ## build data/reina_firme.duckdb from parquet
	uv run pipeline/03_load_duckdb.py

build: extract load
