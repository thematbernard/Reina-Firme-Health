.PHONY: check profile extract load marts docs portable build test evals identity-quality benchmark analysis fingerprint golden server-info serve serve-http demo all

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

identity-quality: ## measure crosswalk precision + recall (no API needed)
	uv run python evals/identity_quality.py

benchmark:    ## time the query path: marts vs raw vs Redshift
	uv run python evals/query_path_benchmark.py

analysis:     ## re-run the strategy analyses and print every number
	uv run python analysis/run.py

server-info:  ## start a fresh server over stdio and print mode + build fingerprint
	uv run python mcp_server/probe.py

fingerprint:  ## print the build fingerprint the MCP server should report
	@uv run python -c "import sys; sys.path.insert(0,'mcp_server'); import server; print(server.build_fingerprint())"

golden:       ## regenerate tests/golden/tool_descriptions.json (review the diff!)
	uv run python -c "import json,sys;sys.path.insert(0,'mcp_server');import server;from pathlib import Path;Path('tests/golden/tool_descriptions.json').write_text(json.dumps({n:' '.join(getattr(server,n).__doc__.split()) for n in ('get_data_dictionary','list_tables','describe_table','run_query')},indent=2,sort_keys=True)+chr(10))"

serve:        ## run the MCP server on stdio (what Claude Desktop uses)
	uv run mcp_server/server.py

serve-http:   ## run the MCP server over streamable HTTP (see docs/roadmap.md before exposing)
	uv run mcp_server/server.py --transport streamable-http --host 127.0.0.1 --port 8000

demo:         ## pane 2: attach a client to the visible `make serve-http` server (run that first)
	@nc -z 127.0.0.1 8000 2>/dev/null || { echo "nothing on 127.0.0.1:8000 — run 'make serve-http' in another pane first"; exit 1; }
	claude --mcp-config .mcp.http.json --strict-mcp-config

portable:     ## export a 7MB PII-free marts-only warehouse (runs without Redshift)
	uv run pipeline/06_export_portable.py

build: extract marts docs portable   ## full rebuild from Redshift
all: build test evals
