.PHONY: check profile extract load marts docs build test evals analysis serve all

check:        ## connectivity smoke test against Redshift
	uv run pipeline/00_connect_check.py

profile:      ## dump schema + date ranges to docs/data-notes.md
	uv run pipeline/01_profile.py

extract:      ## pull Redshift tables to data/raw/*.parquet (skips existing)
	uv run pipeline/02_extract.py

load:         ## build data/reina_firme.duckdb (raw 1:1 mirror of Redshift)
	uv run pipeline/03_load_duckdb.py

marts:        ## build data/warehouse.duckdb — raw views + marts (what the MCP server serves)
	uv run pipeline/04_build_marts.py

docs:         ## regenerate semantic/schema.md from the warehouse
	uv run pipeline/05_gen_schema_doc.py

test:         ## warehouse integrity + MCP guardrails (no LLM, fast)
	uv run pytest tests/ -q

evals:        ## agent-level evals through the MCP tools (needs an Anthropic credential)
	uv run python evals/run.py

analysis:     ## re-run the strategy analyses and print every number
	uv run python analysis/run.py

serve:        ## run the MCP server on stdio
	uv run mcp_server/server.py

build: extract marts docs   ## full rebuild from Redshift
all: build test evals
