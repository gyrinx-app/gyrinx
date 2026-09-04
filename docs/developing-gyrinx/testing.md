# Testing

Gyrinx uses pytest for testing with Django integration. Tests are organized by app and follow consistent patterns.

## Running Tests

### Local Testing

```bash
# Run all tests
pytest

# Run tests for specific app
pytest n23/core/tests/
pytest n23/content/tests/

# Run specific test file
pytest n23/core/tests/test_models_core.py

# Run specific test function
pytest n23/core/tests/test_models_core.py::test_list_creation

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=gyrinx
```

### Full Test Suite

```bash
# Run the full suite against local Postgres (thin wrapper over pytest)
./scripts/test.sh

# Or invoke pytest directly — pyproject.toml already sets -n auto, so this
# runs in parallel by default
pytest

# Continuous test runner
ptw .
```

CI runs the suite against a GitHub Actions service container Postgres in two
jobs — see [.github/workflows/test.yaml](https://github.com/gyrinx-app/gyrinx/blob/main/.github/workflows/test.yaml).

### The Core Suite

Pull requests are gated on the `test` job, which runs the tests marked `core`
plus every test the pull request touched. The `test-full` job runs everything
and reports, but does not block a merge.

```bash
# Run what the required CI job runs
pytest -m core
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
edge case does not.

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

Each worktree has its own database. The session hook automatically sets `DB_NAME` so `pytest` targets the correct database. No extra configuration needed — just run `pytest` from within any worktree.

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

## Common Issues

### Static Files

If tests fail with static file issues, ensure you're not trying to render templates that require collected static files, or run `manage collectstatic --noinput` before testing.

### Database Constraints

When testing models with foreign key constraints, ensure all required related objects are created first.

### History Tracking

When testing models with history tracking, be aware that history records are created automatically and may affect test assertions.
