PYTHON := .venv/bin/python
PORT   := 8008

.PHONY: run migrate shell

run:
	$(PYTHON) manage.py runserver $(PORT)

migrate:
	$(PYTHON) manage.py makemigrations
	$(PYTHON) manage.py migrate

shell:
	$(PYTHON) manage.py shell
