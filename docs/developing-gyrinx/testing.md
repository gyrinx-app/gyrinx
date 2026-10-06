# Testing

Gyrinx uses pytest for testing with Django integration. Tests are organized by app and follow consistent patterns.

## Running Tests

### Local Testing

```bash
# Prefer this worktree's interpreter so PATH cannot pick a sibling checkout
.venv/bin/python -m pytest

# Run tests for specific app
.venv/bin/python -m pytest n23/core/tests/
.venv/bin/python -m pytest n23/content/tests/

# Run specific test file
.venv/bin/python -m pytest n23/core/tests/test_models_core.py

# Run specific test function
.venv/bin/python -m pytest n23/core/tests/test_models_core.py::test_list_creation

# Run with verbose output
.venv/bin/python -m pytest -v

# Run with coverage
.venv/bin/python -m pytest --cov=gyrinx
```

### Full Test Suite

```bash
# Build React assets, then run the full suite against local Postgres
./scripts/test.sh

# Or build the React assets once and invoke pytest directly. pyproject.toml
# already sets -n auto, so this runs in parallel by default. The exporter
# needs the worktree venv on PATH.
PATH="$PWD/.venv/bin:$PATH" npm run js
# Codex: .codex/run.sh npm run js
.venv/bin/python -m pytest

# Continuous test runner
ptw .
```

CI runs the suite against a GitHub Actions service container Postgres in two
jobs — see [.github/workflows/test.yaml](https://github.com/gyrinx-app/gyrinx/blob/main/.github/workflows/test.yaml).

### Paging for failures on main

The `page-on-main-failure` job sends an incident.io alert when `test` (core)
or `test-full` fails on a push to `main`. It waits for both jobs and sends one
alert listing the failed suites, commit and Actions run link. Pull requests,
merge queue runs and failures confined to `fresh-database` do not page.

Store the HTTP alert source's bearer token in the repository Actions secret
`INCIDENT_IO_ALERT_TOKEN` (Settings → Secrets and variables → Actions).
The webhook URL is configured in `test.yaml`. A missing token or rejected
webhook request fails the paging job, making delivery failures visible.

Alerts are deduplicated by repository and test run ID, so delivery retries
and reruns of the same failing run share an alert. Each new failing run
creates a separate alert. Successful runs do not automatically resolve
previous alerts.

To test the real webhook and paging route after merging the workflow:

1. Open **Actions → Tests → Run workflow** and select `main`.
2. Check **Send a real test page via incident.io** and choose the simulated
   failing suite (`core`, `full` or `both`).
3. Run the workflow. Only the paging job runs; the suites and database job
   are skipped. It sends a `[TEST] Gyrinx test paging` alert with
   `test_alert: true` metadata using the same token, webhook, service,
   environment and delivery code as real failures. Its deduplication key
   uses a separate `ci-test` prefix.
4. Check that the paging job succeeds and the alert reaches the expected
   on-call recipient, then resolve the test alert in incident.io.

The manual run sends a real page using the alert source's routing rules.
On `main`, leaving the send checkbox unchecked skips every job and sends
nothing. Manual runs on other branches or tags execute the test and database
jobs and send no paging test alert. This keeps a manual run on a pull request
branch from satisfying the required `test` check without running the suite.

### The Core Suite

Pull requests are gated on the `test` job, which runs the tests marked `core`
plus every test the pull request touched. The `test-full` job runs everything
and reports, but does not block a merge.

```bash
# Run what the required CI job runs
.venv/bin/python -m pytest -m core
```

`core` marks the tests that must never break: fundamental behaviour, a few
end-to-end flows in each edition, and the safety and performance checks (CSRF,
admin login, the state machine, the task queue, the query-count snapshots). A whole file opts in with a module-level mark:

```python
pytestmark = [pytest.mark.django_db, pytest.mark.core]
```

Keep the set small — the job checks it stays between the bounds set in
`test.yaml`, so it cannot quietly grow back into the full suite. A test that
covers a critical flow belongs in it; a test that covers one page or one
edge case does not. The bound counts the tests marked core on the branch,
so a main suite sitting on `CORE_SUITE_MAX` fails the next pull request
that marks another test core. `scripts/check_core_suite_bounds.py` warns when the
count is within 50 of the cap; raise the bound (or unmark tests) before
that happens.

The pull request's own tests join the run through
`scripts/changed_test_paths.py`: it lists the test files the change added or
modified, the directory of any changed `conftest.py`, and the trees whose
conftest imports a changed fixtures module. The root conftest reads that list
from `GYRINX_CHANGED_TEST_PATHS` and marks those tests `core` too. To see what
a branch would pull in:

```bash
scripts/changed_test_paths.py origin/main
```

### Per-Worktree Testing

Each worktree has its own database and its own `.venv`. The session hook
automatically sets `DB_NAME` so tests target this checkout's database. Invoke
pytest as `.venv/bin/python -m pytest` from the worktree you mean: a sibling
worktree's `pytest` on PATH imports that checkout's code and fails with
phantom errors. The root conftest refuses to start when it detects that
mismatch. Two pytest runs in the same worktree also share `test_<DB>_gwN`
names. pytest holds `logs/pytest.lock` for the session, and a
second process exits immediately with the pid that holds it. Wait for that
process, then run one suite. Workers from `-n` are part of the same run and
do not take a second lock.

On a shared Postgres cluster, prefer `-n 4` while another agent is testing.
`out of shared memory` during schema creation, on a cluster that already has
`max_locks_per_transaction = 256`, means those other workers are still creating
tables. Wait for them to finish, then rerun with `-n 4`. Without `--reuse-db`
each run drops and recreates its own test databases, so a run that failed
part-way leaves nothing to clean up.

Do not raise the lock limit again. A machine whose cluster is still on the
default of 64 needs `./scripts/setup-local-postgres.sh` instead; that script
sets 256.

## Test Organization

### Directory Structure

```
gyrinx/
├── content/tests/
│   ├── fixtures/          # Test data fixtures
│   ├── test_content.py     # Content model tests
│   ├── test_equipment.py   # Equipment-specific tests
│   └── ...
├── core/tests/
│   ├── test_models_core.py # Core model tests
│   ├── test_views.py       # View tests
│   ├── test_forms.py       # Form tests
│   └── ...
└── conftest.py             # Global pytest configuration
```

### Test Patterns

#### Database Tests

All tests that use the database must be marked with `@pytest.mark.django_db`:

```python
import pytest
from django.contrib.auth.models import User
from n23.core.models.campaign import Campaign

@pytest.mark.django_db
def test_campaign_creation():
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        public=True
    )
    assert campaign.name == "Test Campaign"
    assert campaign.owner == user
```

#### View Tests

Use Django's test client for testing views:

```python
@pytest.mark.django_db
def test_campaign_detail_view():
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    campaign = Campaign.objects.create(name="Test", owner=user, public=True)

    response = client.get(f"/campaign/{campaign.id}/")
    assert response.status_code == 200
    assert "Test" in response.content.decode()
```

#### Model Tests

Test model methods, validation, and relationships:

```python
@pytest.mark.django_db
def test_list_fighter_cost_calculation():
    # Test that fighter costs are calculated correctly
    # including equipment assignments
    pass
```

#### Background Task Tests

By default (eager mode) `task.enqueue()` runs the task synchronously, so a test can enqueue and then assert on the effect. To exercise Pub/Sub-like adverse conditions — duplicate delivery, transient failure, message loss — add the `task_queue` fixture, which flips the backend to `manual` mode and lets the test drive delivery:

```python
@pytest.mark.django_db
def test_cost_change_is_idempotent(task_queue, ...):
    with task_queue.capture():        # fire the on_commit enqueue
        change_content_cost(...)
    task_queue.deliver_all()          # deliver once
    task_queue.redeliver_last()       # at-least-once duplicate
    assert ...                        # effect applied exactly once
```

See [How-to: Test Redelivery, Failure, and Message Loss](../how-to-guides/task-framework.md#test-redelivery-failure-and-message-loss-the-task_queue-fixture) for the full fixture API.

## Test Configuration

### Static Files

Tests are configured to use `StaticFilesStorage` instead of `CompressedManifestStaticFilesStorage` to avoid manifest issues during testing. This is handled in `conftest.py`.

### Database

Tests use a separate test database created by pytest-django. In local development, each worktree has its own database (`gyrinx_wt_{hash}`) and its own set of test databases. The schema is rebuilt from current model definitions on every run via `--nomigrations` (configured in `pyproject.toml`), so model changes are picked up automatically. Pass `--reuse-db` explicitly if you want to skip the rebuild for a tight focused-test loop — be aware this reintroduces the stale-schema risk if you then change a model.

### Fixtures

Use fixtures for common test data:

```python
@pytest.fixture
def sample_user():
    return User.objects.create_user(username="testuser", password="testpass")

@pytest.fixture
def sample_campaign(sample_user):
    return Campaign.objects.create(
        name="Test Campaign",
        owner=sample_user,
        public=True
    )
```

## Writing Good Tests

### Test Naming

- Use descriptive test names that explain what is being tested
- Follow the pattern: `test_<what>_<condition>_<expected_result>`

### Test Structure

Follow the Arrange-Act-Assert pattern:

```python
def test_campaign_creation():
    # Arrange
    user = User.objects.create_user(username="testuser", password="testpass")

    # Act
    campaign = Campaign.objects.create(name="Test", owner=user, public=True)

    # Assert
    assert campaign.name == "Test"
    assert campaign.owner == user
```

### Test Coverage

- Test happy paths and edge cases
- Test model validation and constraints
- Test view permissions and responses
- Test form validation
- Test complex business logic

### Performance

- Use `pytest-django`'s database optimization features
- Avoid unnecessary database hits in tests
- Use factories or fixtures for test data creation

## Integration with CI/CD

Tests are automatically run in GitHub Actions on every pull request and push to main. The test suite must pass before code can be merged.

### Reading a failed job while the run is still going

`gh run view --log-failed` waits until every job in the workflow run has
finished. A completed job (for example the required `test` job) already
exposes logs on `GET .../actions/jobs/JOB_ID/logs` while `test-full` is still
running:

```bash
python scripts/fetch_job_logs.py
python scripts/fetch_job_logs.py 2667
python scripts/fetch_job_logs.py --job 108503680591
```

The helper filters for pytest `FAILURES` rather than the Post job cleanup /
container tail. An in-progress job's latest chunk can lag several minutes.
Load the `ci-job-logs` skill. Do not use `gh run view --log-failed` to watch a
run that has not finished.

## Common Issues

### Static Files

If tests fail with static file issues, ensure you're not trying to render templates that require collected static files, or run `manage collectstatic --noinput` before testing.

### Database Constraints

When testing models with foreign key constraints, ensure all required related objects are created first.

### History Tracking

When testing models with history tracking, be aware that history records are created automatically and may affect test assertions.
