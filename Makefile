.PHONY: run dry-run test daemon venv docker-build docker-up docker-down docker-logs docker-cycle docker-dry-run

# Ativação rápida ou comandos diretos usando o .venv

venv:
	@echo "Para ativar o venv no seu terminal, execute:"
	@echo "source .venv/bin/activate"

run:
	@.venv/bin/python scripts/run_cycle.py

dry-run:
	@.venv/bin/python scripts/run_cycle.py --dry-run -v

test:
	@.venv/bin/pytest -v tests/

daemon:
	@.venv/bin/python scripts/schedule_daemon.py

# Comandos Docker (Full Docker em VPS)

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
