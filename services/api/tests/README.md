# Integration Tests

End-to-end integration tests for the PrompTrading API.

## Prerequisites

### 1. Start Docker Compose Dev Environment

```bash
cd infra/compose
docker compose -f docker-compose.dev.yml up -d

# Verify services are running
docker compose -f docker-compose.dev.yml ps

# Wait for API to be ready
docker compose -f docker-compose.dev.yml logs api | grep "Application startup"
```

### 2. Install Test Dependencies

```bash
# If running locally (not inside container)
cd services/api
pip install -e '.[test]'

# Test dependencies are already installed in the API image
docker compose -f docker-compose.dev.yml exec api pytest -q
```

### 3. No LLM API Key Required

These tests use the **fallback strategy**, which does NOT require an LLM API key.

The agent automatically falls back to a simple moving average crossover strategy when no API key is provided.

## Running Tests

### Run All Integration Tests

```bash
# From inside the API container
docker compose -f docker-compose.dev.yml exec api pytest tests/test_integration_workflow.py -v -m integration

# Or from host (if dependencies installed)
cd services/api
pytest tests/test_integration_workflow.py -v -m integration
```

### Run Specific Test

```bash
# Run only the main E2E test
pytest tests/test_integration_workflow.py::test_e2e_generate_and_backtest_with_fallback -v

# Run only edge case tests
pytest tests/test_integration_workflow.py::test_invalid_dataset_parameters -v
```

### Run with Coverage

```bash
pytest tests/ --cov=app --cov-report=html --cov-report=term

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Run with Verbose Logging

```bash
pytest tests/test_integration_workflow.py -v -s --log-cli-level=INFO
```

## Expected Test Execution Time

| Test | Expected Time |
|------|---------------|
| `test_e2e_generate_and_backtest_with_fallback` | 2-3 minutes |
| Edge case tests | < 5 seconds each |
| **Total** | **~3-5 minutes** |

The main E2E test takes longer because it:
1. Creates strategy version
2. Spawns agent Docker container (generates fallback strategy)
3. Spawns backtest Docker container (runs backtest)
4. Waits for worker to process jobs
5. Validates artifacts

## Test Architecture

### What Gets Tested

```
User Request
    ↓
FastAPI TestClient (HTTP)
    ↓
API Endpoints (backtests.py)
    ↓
Database (PostgreSQL) + Redis Queue
    ↓
Worker Service (Docker)
    ↓
Agent Container (Docker) → Generates fallback strategy
    ↓
Backtest Container (Docker) → Runs backtest
    ↓
Artifacts (metrics.json, trades.json, equity_curve.json)
    ↓
Validation (pytest asserts)
```

### Database Isolation

Each test runs in a clean database state:
1. Test begins → Transaction starts
2. Test creates data (User, Strategy, Job, etc.)
3. Test ends → Transaction rolls back
4. Database is clean for next test

### Key Fixtures

- `test_db_session`: Database session with transaction rollback
- `test_redis`: Redis connection
- `test_app`: FastAPI TestClient with dependency overrides
- `test_user`: Authenticated test user with session
- `test_strategy`: Test strategy with user as ADMIN
- `wait_for_job_completion()`: Helper to poll job status

## Troubleshooting

### Test Fails with "Database Not Ready"

```bash
# Check PostgreSQL is running
docker compose -f docker-compose.dev.yml logs postgres | tail -20

# Restart PostgreSQL if needed
docker compose -f docker-compose.dev.yml restart postgres
```

### Test Fails with "Redis Not Ready"

```bash
# Check Redis is running
docker compose -f docker-compose.dev.yml logs redis | tail -20

# Restart Redis if needed
docker compose -f docker-compose.dev.yml restart redis
```

### Test Fails with "Worker Timeout"

```bash
# Check worker logs
docker compose -f docker-compose.dev.yml logs worker | tail -50

# Verify worker is processing jobs
docker compose -f docker-compose.dev.yml logs worker | grep "Processing job"
```

### Test Fails with "Job Failed"

Check the worker logs for detailed error messages:
```bash
docker compose -f docker-compose.dev.yml logs worker | grep -A 20 "FAILED"
```

Common causes:
- Docker daemon not accessible
- Backtest image not built
- Network issues between containers

### TimeoutError: Job did not complete

The main E2E test has a 10-minute timeout. If it consistently times out:

1. Check worker is running: `docker compose -f docker-compose.dev.yml ps worker`
2. Check worker logs for errors
3. Verify Docker images are built: `docker images | grep backtest`
4. Check available disk space (backtests generate artifacts)

## CI/CD Integration

### Pre-commit Hook (Optional)

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash
cd services/api
pytest tests/test_integration_workflow.py -v -m integration --timeout=300
```

### GitHub Actions Example

```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: prompt-trading
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'

      - name: Install dependencies
        run: |
          cd services/api
          pip install -e '.[test]'

      - name: Run integration tests
        env:
          APP_DB_URL: postgresql://postgres:postgres@localhost:5432/prompt-trading
          APP_REDIS_URL: redis://localhost:6379/0
        run: |
          cd services/api
          pytest tests/test_integration_workflow.py -v -m integration --timeout=600
```

## Adding New Tests

### Template for New Integration Test

```python
import pytest
from conftest import wait_for_job_completion

@pytest.mark.integration
def test_your_new_feature(test_app, test_user, test_strategy):
    """Description of what this test validates."""

    # 1. Setup: Prepare request data
    request_data = {...}

    # 2. Act: Call API endpoint
    response = test_app.post(
        f"/api/endpoint",
        json=request_data,
        cookies=test_user["cookies"],
    )

    # 3. Assert: Validate response
    assert response.status_code == 200
    data = response.json()

    # 4. Additional assertions...
    assert "expected_field" in data
```

## Best Practices

1. **Use fixtures**: Always use `test_user["cookies"]` for authenticated requests
2. **Clean up**: Don't worry about DB cleanup, transactions auto-rollback
3. **Isolation**: Each test should be independent and runnable alone
4. **Descriptive names**: Use `test_what_is_being_tested` naming convention
5. **Mark tests**: Use `@pytest.mark.integration` for E2E tests
6. **Timeouts**: Set appropriate timeouts for long-running tests

## References

- [pytest documentation](https://docs.pytest.org/)
- [FastAPI Testing docs](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy 2.0 docs](https://docs.sqlalchemy.org/en/20/)
