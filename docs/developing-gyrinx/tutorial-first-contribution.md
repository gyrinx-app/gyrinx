# Tutorial: Your First Contribution

This tutorial walks you through making your first code contribution to Gyrinx. You'll add a simple page, write tests for it, and follow the complete development workflow.

## What You'll Learn

- How to set up your development environment
- How to create a view and template following Gyrinx patterns
- How to write tests for your code
- How to format code and run the test suite
- How to create a pull request

## Prerequisites

- Python 3.12+ installed
- Docker with Compose installed
- Git installed
- Basic familiarity with Django

## Time Required

Approximately 45-60 minutes

---

## Step 1: Set Up Your Development Environment

If you haven't already, clone the repository and set up your environment:

```bash
git clone git@github.com:gyrinx-app/gyrinx.git
cd gyrinx

# Create virtual environment
python -m venv .venv && . .venv/bin/activate

# Install dependencies
pip install --editable .

# Set up environment variables
manage setupenv

# Set up frontend toolchain
nodeenv -p && npm install && npm run build

# Install pre-commit hooks
pre-commit install

# Start database and run migrations
docker compose up -d && manage migrate
```

**Checkpoint:** Run `manage runserver` and visit http://localhost:8000 to verify the app works.

---

## Step 2: Create a New Branch

Always work on a feature branch:

```bash
git checkout -b tutorial-example-page
```

---

## Step 3: Create Your View

Let's add a simple "About Development" page to the pages app.

Create the view in `gyrinx/pages/views.py`. First, check what's already there:

```bash
cat gyrinx/pages/views.py
```

Add a new view function:

```python
# In gyrinx/pages/views.py

def about_development(request):
    """Display information about contributing to Gyrinx development."""
    return render(request, "pages/about_development.html")
```

**Key points:**

- Views are simple functions that take a `request` and return a response
- We use `render()` to render a template
- Template paths are relative to the templates directory

---

## Step 4: Create the URL Route

Add the URL pattern in `gyrinx/pages/urls.py`:

```python
# Add to urlpatterns list
path("about-development/", views.about_development, name="about-development"),
```

**Key points:**

- URL patterns use `path()` with a route, view function, and name
- The name is used for reverse URL lookups in templates

---

## Step 5: Create the Template

Create the template at `gyrinx/pages/templates/pages/about_development.html`:

```html
{% extends "core/layouts/page.html" %}

{% block title %}About Development{% endblock %}

{% block content %}
<div class="container">
    <div class="row">
        <div class="col-12 col-xl-6">
            <h1>Contributing to Gyrinx</h1>

            <p class="lead">
                Gyrinx is open source and welcomes contributions from the community.
            </p>

            <h2>Getting Started</h2>
            <p>
                Check out our
                <a href="https://github.com/gyrinx-app/gyrinx">GitHub repository</a>
                for setup instructions and contribution guidelines.
            </p>

            <h2>Technical Stack</h2>
            <ul>
                <li>Django web framework</li>
                <li>PostgreSQL database</li>
                <li>Bootstrap 5 frontend</li>
                <li>Google Cloud Platform hosting</li>
            </ul>
        </div>
    </div>
</div>
{% endblock %}
```

**Key points:**

- Extend `core/layouts/page.html` for simple content pages
- Use `col-12 col-xl-6` for mobile-first responsive layout
- Keep content in a single column that expands on larger screens

---

## Step 6: Write Tests

Create a test file at `gyrinx/pages/tests/test_views.py` (create the `tests` directory if needed):

```python
import pytest
from django.test import Client


@pytest.mark.django_db
def test_about_development_page_loads():
    """Test that the about development page returns 200."""
    client = Client()
    response = client.get("/about-development/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_about_development_page_content():
    """Test that the about development page contains expected content."""
    client = Client()
    response = client.get("/about-development/")
    content = response.content.decode()
    assert "Contributing to Gyrinx" in content
    assert "GitHub" in content
```

**Key points:**

- Use `@pytest.mark.django_db` for any test that touches the database
- Use Django's `Client` for view testing
- Test both that the page loads (status code) and contains expected content

---

## Step 7: Run Tests

Run your tests to make sure they pass:

```bash
# Run just your new tests
pytest gyrinx/pages/tests/test_views.py -v

# Run the full test suite
pytest -n auto
```

**Checkpoint:** All tests should pass.

---

## Step 8: Format Your Code

Before committing, format your code:

```bash
./scripts/fmt.sh
```

This runs:

- `ruff` for Python linting and formatting
- `djlint` for template formatting
- Other code quality checks

---

## Step 9: Verify Locally

Start the development server and check your work:

```bash
manage runserver
```

Visit http://localhost:8000/about-development/ to see your new page.

**Checkpoint:** The page should display with proper styling and content.

---

## Step 10: Commit Your Changes

Stage and commit your changes:

```bash
git add .
git commit -m "feat: add about development page

Add a simple page explaining how to contribute to Gyrinx development.
Includes view, template, URL route, and tests."
```

The pre-commit hooks will run automatically to check formatting.

---

## Step 11: Push and Create a Pull Request

Push your branch and create a PR:

```bash
git push -u origin tutorial-example-page
```

Then create a pull request on GitHub with:

- A clear title describing the change
- A description explaining what and why
- Reference any related issues

---

## What You Built

You've successfully:

1. Set up a Gyrinx development environment
2. Created a Django view following project patterns
3. Added a URL route
4. Built a mobile-first template using Bootstrap
5. Written pytest tests
6. Formatted code and run the test suite
7. Created a commit following project conventions

## Next Steps

- Read [Key Concepts](key-concepts.md) to understand the project architecture
- Explore [Models and Database](models-and-database.md) to learn about the data layer
- Check [Frontend Development](frontend-development.md) for styling guidelines
- Review [Testing](testing.md) for comprehensive testing patterns
- Join the [Discord](https://discord.gg/jamrJPYC) to discuss ideas with the team

## Cleaning Up

If you were just following along and don't want to submit this example:

```bash
git checkout main
git branch -D tutorial-example-page
```
