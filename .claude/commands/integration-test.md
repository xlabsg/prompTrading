---
description: Run end-to-end integration tests for the Stratsmith
---

# Integration Tests

Use the **integration-test** skill to run end-to-end integration tests.

## Quick Start

Run all integration tests:
```bash
cd services/api
./run_tests.sh
```

## What It Tests

- Strategy generation (fallback mode, no LLM required)
- Backtest execution with real Docker containers
- API endpoints and error handling
- Job queue processing
- Artifact generation and validation

## Expected Time

- **First run**: ~5 minutes (Docker images need to be built)
- **Subsequent runs**: ~3 minutes (images cached)

## Prerequisites

Docker Compose dev environment must be running:
```bash
cd infra/compose
./update.sh
```

## Options

### Run specific test
```bash
cd services/api
../infra/compose/docker-compose.dev.yml exec api pytest \
  tests/test_integration_workflow.py::test_e2e_generate_and_backtest_with_fallback -v
```

### Run with coverage
```bash
cd services/api
../infra/compose/docker-compose.dev.yml exec api pytest \
  tests/ --cov=app --cov-report=html --cov-report=term
```

### Run with verbose output
```bash
cd services/api
../infra/compose/docker-compose.dev.yml exec api pytest \
  tests/test_integration_workflow.py -v -s --log-cli-level=INFO
```

## Troubleshooting

If tests fail, check worker logs:
```bash
docker compose -f docker-compose.dev.yml logs worker | tail -100
```

For detailed diagnostics, see the [integration-test skill](../skills/integration-test/SKILL.md).
