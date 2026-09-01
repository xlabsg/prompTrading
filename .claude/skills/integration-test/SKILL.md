---
name: integration-test
description: Run end-to-end integration tests for the Stratsmith. Use when user asks to run, execute, or check integration tests. Supports running all tests, specific tests, with coverage, or in verbose mode. Automatically handles Docker Compose environment checks.
tools: Bash, Read
---

# Integration Test Runner

Run end-to-end integration tests for the Stratsmith. Tests validate the complete workflow from strategy generation to backtesting using real Docker containers.

## When to Use

- User asks to "run integration tests", "run e2e tests", "check tests"
- User wants to verify the system works before committing code
- User needs to validate changes don't break existing functionality
- User requests test coverage report

## Prerequisites Check

Before running tests, verify Docker Compose environment is ready:

```bash
cd infra/compose
docker compose -f docker-compose.dev.yml ps --format json | python3 -c "
import json, sys
services = json.load(sys.stdin)
running = [s['Service'] for s in services if s['State'] == 'running']
required = ['api', 'worker', 'postgres', 'redis']
missing = [s for s in required if s not in running]
if missing:
    print(f'Missing services: {missing}')
    sys.exit(1)
print('All required services running')
" 2>/dev/null
```

If services are not running, start them first:

```bash
cd infra/compose
./update.sh
```

## Test Commands

### Run All Integration Tests

```bash
cd services/api
./run_tests.sh
```

**Expected output:**
- Main E2E test: 2-3 minutes
- Edge case tests: < 5 seconds each
- Total: ~3-5 minutes

### Run Specific Test

```bash
cd services/api
../infra/compose/docker-compose.dev.yml exec api pytest \
  tests/test_integration_workflow.py::test_e2e_generate_and_backtest_with_fallback -v
```

**Available tests:**
- `test_e2e_generate_and_backtest_with_fallback` - Full workflow test
- `test_invalid_dataset_parameters` - Input validation
- `test_strategy_not_found` - 404 handling
- `test_unauthorized_access` - Auth requirement
- `test_concurrent_job_limit` - Concurrency control

### Run with Coverage

```bash
cd services/api
../infra/compose/docker-compose.dev.yml exec api pytest \
  tests/ --cov=app --cov-report=html --cov-report=term
```

Coverage report generated in `htmlcov/index.html`.

### Run with Verbose Output

```bash
cd services/api
../infra/compose/docker-compose.dev.yml exec api pytest \
  tests/test_integration_workflow.py -v -s --log-cli-level=INFO
```

## Interpreting Results

### Success Indicators

```
✓ test_e2e_generate_and_backtest_with_fallback PASSED
✓ test_invalid_dataset_parameters PASSED
✓ test_strategy_not_found PASSED
✓ test_unauthorized_access PASSED
✓ test_concurrent_job_limit PASSED

===== 5 passed in 183.45s =====
```

### Failure Diagnostics

If tests fail, check:

1. **Worker logs** (most common issue):
   ```bash
   docker compose -f docker-compose.dev.yml logs worker | tail -100
   ```

2. **API logs**:
   ```bash
   docker compose -f docker-compose.dev.yml logs api | tail -50
   ```

3. **Docker containers**:
   ```bash
   docker compose -f docker-compose.dev.yml ps
   ```

4. **Job status** (if timeout):
   ```bash
   docker compose -f docker-compose.dev.yml exec api python -c "
   from control_plane.db import create_db_engine, create_session_factory
   from control_plane.models import Job
   from sqlalchemy import select, desc

   engine = create_db_engine('postgresql://postgres:postgres@db:5432/stratsmith')
   session_factory = create_session_factory(engine)

   with session_factory() as db:
       jobs = db.execute(select(Job).order_by(desc(Job.created_at)).limit(5)).scalars().all()
       for job in jobs:
           print(f'{job.id[:8]}... | {job.type} | {job.status} | {job.error_message or \"OK\"}')
   "
   ```

## Common Issues and Solutions

### Issue: "Docker Compose is not running"

**Solution:**
```bash
cd infra/compose
./update.sh
```

### Issue: "Test timeout after 600s"

**Possible causes:**
1. Worker not processing jobs
2. Docker image missing
3. Network issues

**Diagnosis:**
```bash
# Check worker is processing
docker compose -f docker-compose.dev.yml logs worker | grep "Processing job"

# Check backtest image exists
docker images | grep backtest

# Check network
docker network inspect stratsmith_dev
```

### Issue: "Job failed"

**Check error details:**
```bash
docker compose -f docker-compose.dev.yml logs worker | grep -A 20 "FAILED"
```

### Issue: "Database connection error"

**Restart database:**
```bash
docker compose -f docker-compose.dev.yml restart postgres
# Wait 5 seconds for startup
sleep 5
```

## Test Architecture

```
Test (pytest)
    ↓
FastAPI TestClient (HTTP)
    ↓
API Endpoints (backtests.py)
    ↓
PostgreSQL + Redis
    ↓
Worker Service (Docker)
    ↓
Agent Container → Generates fallback strategy
    ↓
Backtest Container → Runs backtest
    ↓
Artifacts validated
```

## What Gets Tested

| Component | Validation |
|-----------|------------|
| Strategy generation | Fallback strategy code generation |
| Job queue | Redis queue processing |
| Worker execution | Docker container spawning |
| Backtest engine | Strategy execution on historical data |
| Artifacts | metrics.json, trades.json, equity_curve.json |
| API responses | Status codes, data structures |
| Error handling | Invalid inputs, auth, 404s |
| Concurrency | Job collision prevention |

## Coverage Goals

Target coverage: **70%+** for critical paths:

- Strategy generation: `packages/agent/`
- Backtest execution: `packages/backtest/`
- API endpoints: `services/api/app/routers/`
- Worker job processing: `services/worker/worker/`

## CI/CD Integration

### Pre-commit Hook

```bash
# .git/hooks/pre-commit
#!/bin/bash
cd services/api
./run_tests.sh
```

### GitHub Actions

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
          POSTGRES_DB: stratsmith
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
      - name: Run tests
        run: |
          cd services/api
          pytest tests/test_integration_workflow.py -v -m integration --timeout=600
```

## Tips for Users

1. **First run takes longer** - Docker images need to be built (~5 minutes)
2. **Subsequent runs are faster** - Images cached, tests take ~3 minutes
3. **No LLM required** - Tests use fallback strategy automatically
4. **Run frequently** - Tests catch regressions early
5. **Check logs first** - Worker logs contain detailed error messages

## Advanced: Creating New Tests

To add a new integration test:

1. Create test in `services/api/tests/test_integration_workflow.py`
2. Use existing fixtures: `test_app`, `test_user`, `test_strategy`
3. Mark with `@pytest.mark.integration`
4. Follow naming convention: `test_what_is_being_tested`

Example:

```python
@pytest.mark.integration
def test_your_new_feature(test_app, test_user, test_strategy):
    """Test your new feature end-to-end."""
    response = test_app.post(
        f"/strategies/{test_strategy}/your-endpoint",
        json={"key": "value"},
        cookies=test_user["cookies"],
    )
    assert response.status_code == 200
    # Additional assertions...
```
