.PHONY: run dry-run test daemon venv

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
