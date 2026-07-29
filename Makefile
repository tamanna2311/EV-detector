.PHONY: install dev test lint format train docker

install:
	python -m pip install -r requirements-dev.txt

dev:
	uvicorn app.main:app --reload --port 8000

test:
	pytest --cov=app --cov-report=term-missing

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

train:
	python scripts/train_model.py --train-dir "$${TRAIN_DIR}" --test-dir "$${TEST_DIR}"

docker:
	docker build -t ev-detector .
