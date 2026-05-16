# Testing

Gyrinx uses pytest for testing with Django integration. Tests are organized by app and follow consistent patterns.

## Running Tests

### Local Testing

```bash
# Run all tests
pytest

# Run tests for specific app
pytest gyrinx/core/tests/
pytest gyrinx/content/tests/

# Run specific test file
pytest gyrinx/core/tests/test_models_core.py

# Run specific test function
pytest gyrinx/core/tests/test_models_core.py::test_list_creation

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

CI runs the same `pytest` invocation against a GitHub Actions service container
Postgres — see [.github/workflows/test.yaml](https://github.com/gyrinx-app/gyrinx/blob/main/.github/workflows/test.yaml).

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
from gyrinx.core.models.campaign import Campaign

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
