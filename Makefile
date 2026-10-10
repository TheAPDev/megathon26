PY ?= python3
.PHONY: all install data train eval test serve sql docker web web-dev web-test e2e contract
all: data train eval test           ## full reproducible pipeline (seed 42)
install:
	$(PY) -m pip install -r requirements.txt
data:                               ## synthetic population, benchmarks, portfolio scores (~3 min)
	$(PY) scripts/generate_data.py --n 50000 --seed 42
train:                              ## energy, ranker and value models + reports/eval_report.json
	$(PY) -m greenghar.ml.train
eval:                               ## LLM groundedness evaluation -> reports/llm_eval.json
	$(PY) scripts/llm_eval.py --n 30
test:
	$(PY) -m pytest -q
serve:
	uvicorn greenghar.api.main:app --host 0.0.0.0 --port 8000
sql:                                ## regenerate reference-data SQL from the CSVs
	$(PY) scripts/export_reference_sql.py
docker:
	docker compose up --build
web:                                ## build the web app into frontend/dist (served by the API at /app)
	cd frontend && npm ci --no-audit --no-fund && npm run build
web-dev:                            ## Vite dev server on :5173, proxying API calls to :8000
	cd frontend && npm run dev
web-test:                           ## typecheck, lint, unit/component tests
	cd frontend && npm run typecheck && npm run lint && npm test
e2e:                                ## Playwright end-to-end tests against a real backend (starts one on :8765)
	cd frontend && npm run build && npx playwright test
contract:                           ## check a running API (:8000) against the fields the UI reads
	cd frontend && node scripts/contract-check.mjs http://127.0.0.1:8000
