.PHONY: run dry-run test lint eval check daemon venv monitors monitors-dashboard smartphones smartwatches suportes docker-build docker-up docker-down docker-logs docker-cycle docker-dry-run

venv:
	@echo "Para ativar o venv no seu terminal, execute:"
	@echo "source .venv/bin/activate"

run:
	@.venv/bin/python scripts/run_cycle.py

dry-run:
	@.venv/bin/python scripts/run_cycle.py --dry-run -v

lint:
	@.venv/bin/ruff check src scripts tests docker

test:
	@.venv/bin/pytest -v tests/

eval:
	@.venv/bin/python scripts/evaluate_agents.py -q

check: lint test eval

daemon:
	@.venv/bin/python scripts/schedule_daemon.py

monitors:
	@.venv/bin/python scripts/track_monitors_27.py

monitors-dashboard:
	@.venv/bin/python scripts/track_monitors_27.py --dashboard-only --no-open

smartphones:
	@.venv/bin/python scripts/track_smartphones_512.py

smartwatches:
	@.venv/bin/python scripts/track_smartwatches.py

suportes:
	@.venv/bin/python scripts/track_monitor_arms.py

docker-build:
	@docker compose build

docker-up:
	@docker compose up -d
	@echo "🛰️ PromoRadar Daemon iniciado em segundo plano no Docker."

docker-down:
	@docker compose down

docker-logs:
	@docker compose logs -f

docker-cycle:
	@docker compose run --rm promoradar-cli

docker-dry-run:
	@docker compose run --rm promoradar-cli --dry-run
