.PHONY: demo test eval lint clean install docker-up

# ── Setup ──────────────────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt -r requirements-dev.txt

# ── Demo: full local pipeline, no external deps ───────────────────────────────
demo:
	@echo "==> Checking .env..."
	@if not exist .env (copy .env.example .env)
	@echo "==> Training model (if not already trained)..."
	@if not exist models\scorer_v1.joblib (python eval\train.py)
	@echo "==> Starting SentinelLens dashboard on http://localhost:5000"
	@echo "    Default credentials: admin / changeme"
	flask --app sentinellens.api.app run --host=0.0.0.0 --port=5000

# ── Eval: train model + produce evaluation report ─────────────────────────────
eval:
	python eval/train.py

# ── Tests ──────────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v --cov=sentinellens --cov-report=term-missing

# ── Lint ───────────────────────────────────────────────────────────────────────
lint:
	ruff check sentinellens/ tests/
	black --check sentinellens/ tests/
	bandit -r sentinellens/ -ll

# ── Clean ──────────────────────────────────────────────────────────────────────
clean:
	del /f /s /q sentinellens\__pycache__ 2>nul
	del /f /q *.db 2>nul
	del /f /q .coverage 2>nul

# ── Docker ─────────────────────────────────────────────────────────────────────
docker-up:
	docker compose up --build
