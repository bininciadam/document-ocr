.PHONY: dev test test-py test-ts build benchmark benchmark-kyc docker-build install sync

install:
	uv sync
	cd packages/passport-ocr && npm ci

dev:
	PYTHONPATH=$(PWD) uv run uvicorn deploy.docker.server:app --host 0.0.0.0 --port 8000 --reload --reload-dir core --reload-dir deploy/docker

test: test-py test-ts

test-py:
	uv run pytest tests/python -v

test-ts:
	cd packages/passport-ocr && npm test

build:
	cd packages/passport-ocr && npm run build

benchmark:
	uv run python benchmarks/accuracy.py

benchmark-kyc:
	@test -n "$(KYC_MANIFEST)" || (echo "Set KYC_MANIFEST=/secure/path/manifest.json"; exit 2)
	uv run python benchmarks/kyc_accuracy.py --manifest "$(KYC_MANIFEST)" $(if $(KYC_DATASET_ROOT),--dataset-root "$(KYC_DATASET_ROOT)",) $(if $(KYC_REPORT),--output "$(KYC_REPORT)",)

sync:
	cd packages/passport-ocr && bash scripts/sync-python.sh

docker-build:
	docker build -f deploy/docker/Dockerfile -t passport-ocr .
