# Integration Test Skill - Usage Guide

## What Was Created

A Claude Skill has been created to run integration tests for the Stratsmith. This allows AI assistants to execute end-to-end tests automatically when requested.

```
.claude/
├── skills/
│   └── integration-test/
│       └── SKILL.md          # Main skill definition
└── commands/
    └── integration-test.md   # Quick command reference
```

## How to Use

### For Users (Requesting Tests)

Simply ask Claude to run tests in any of these ways:

```
"Run the integration tests"
"Execute the e2e tests"
"Check if everything works"
"Run tests before I commit"
"Test the backtest workflow"
```

Claude will automatically:
1. Check if Docker Compose is running
2. Start services if needed
3. Execute the integration tests
4. Report results and diagnose any failures

### For AI Assistants (Invoking the Skill)

The skill is automatically invoked when:
- User mentions "integration test", "e2e test", "run tests"
- User asks to verify functionality before committing
- User requests validation of changes
- User mentions test coverage or validation

## Skill Capabilities

### ✅ Automatic Environment Checks

- Verifies Docker Compose services are running
- Checks required services (api, worker, postgres, redis)
- Starts services if needed (with user confirmation)

### ✅ Flexible Test Execution

- Run all tests
- Run specific test cases
- Run with coverage report
- Run with verbose logging
- Run subset (fast/slow/integration markers)

### ✅ Result Interpretation

- Parses test output
- Identifies success/failure
- Diagnoses common issues
- Provides actionable fixes

### ✅ Troubleshooting

- Checks worker logs for errors
- Verifies job status in database
- Inspects Docker containers
- Provides targeted solutions

## Example Conversations

### Example 1: Basic Test Run

```
User: Run the integration tests

Claude: I'll run the integration tests for you.

[Checks Docker Compose]
[Executes tests]
[Reports results]

✅ All 5 tests passed in 183.45s
```

### Example 2: Pre-commit Validation

```
User: I'm about to commit this code, can you test it?

Claude: Good idea! Let me run the integration tests to validate your changes.

[Runs tests]
[Checks coverage]
[Validates no regressions]

✅ Tests passed! Your changes look good to commit.
```

### Example 3: Specific Test

```
User: Test just the backtest workflow

Claude: I'll run the backtest workflow test specifically.

[Executes test_e2e_generate_and_backtest_with_fallback]
[Validates artifacts]
[Checks worker logs]

✅ Backtest workflow test passed in 142.3s
```

### Example 4: Failure Diagnosis

```
User: Tests are failing, help me debug

Claude: Let me check what's happening.

[Checks worker logs]
[Verifies Docker containers]
[Checks job status]

🔍 Found the issue: Worker can't spawn backtest container
💡 Solution: Backtest Docker image is missing
→ Run: cd infra/compose && docker compose -f docker-compose.dev.yml build backtest
```

## Integration with Development Workflow

### Pre-commit Hook

Add to `.git/hooks/pre-commit`:
```bash
#!/bin/bash
echo "Running integration tests..."
cd services/api
./run_tests.sh
```

### CI/CD Pipeline

The skill generates GitHub Actions configuration - see the skill file for full example.

### Before Release

```
User: We're about to deploy, run full test suite

Claude: Running comprehensive test suite...

[All integration tests]
[Coverage report]
[Performance metrics]

✅ Ready for deployment!
```

## Skill Metadata

**Name:** `integration-test`
**Tools:** Bash, Read
**Description:** Run end-to-end integration tests for the Stratsmith

## Advanced Usage

### Custom Test Selection

```
User: Run only the fast tests

Claude: [Runs tests marked with @pytest.mark.fast]
```

### With Coverage Report

```
User: Run tests and show me coverage

Claude: [Executes tests with --cov]
[Generates HTML coverage report]
📊 Coverage: 78.5% - View htmlcov/index.html
```

### Parallel Execution

```
User: Run tests in parallel

Claude: [Executes pytest with -xauto]
[Runs multiple tests simultaneously]
```

## Troubleshooting the Skill

If Claude doesn't invoke the skill:

1. **Check skill is registered:**
   ```bash
   ls -la .claude/skills/integration-test/SKILL.md
   ```

2. **Use explicit command:**
   ```
   "Use the integration-test skill to run tests"
   ```

3. **Mention key phrases:**
   - "integration test"
   - "e2e test"
   - "run tests"
   - "verify functionality"

## Related Documentation

- **Test implementation:** `services/api/tests/README.md`
- **Test framework:** `services/api/tests/conftest.py`
- **Test cases:** `services/api/tests/test_integration_workflow.py`
- **Implementation summary:** `services/api/INTEGRATION_TEST_SUMMARY.md`

## Future Enhancements

Potential improvements to the skill:

1. **Performance testing** - Add load testing capabilities
2. **Regression detection** - Compare results against baseline
3. **Flaky test detection** - Retry failed tests automatically
4. **Test result history** - Track test outcomes over time
5. **Auto-fix on failure** - Attempt to fix common issues

## Support

If the skill doesn't work as expected:

1. Check Docker Compose is running
2. Verify test dependencies are installed
3. Check `.claude/skills/integration-test/SKILL.md` exists
4. Review test logs in `services/api/tests/`

---

**Created:** 2026-01-24
**Version:** 1.0.0
**Status:** Production Ready ✅
