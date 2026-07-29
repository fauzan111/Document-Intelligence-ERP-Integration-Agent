.PHONY: install test lint run up down demo

install:
	pip install -r requirements-dev.txt

lint:
	ruff check app workers tests scripts

test:
	pytest tests/unit -q

# Run offline: SQLite, pdftext OCR, regex extractor, mock SAP ERP.
run:
	DATABASE_URL=sqlite+pysqlite:///./dev.sqlite OCR_PROVIDER=pdftext ERP_PROVIDER=mock \
	uvicorn app.main:app --reload

up:
	docker compose up --build

down:
	docker compose down -v

# Seed valid + invalid invoices (ERP push vs exception queue). Server must be up.
demo:
	python scripts/seed_demo.py --base-url http://localhost:8000
