# Integration Testing Guide

This guide explains how to write integration tests for the Gyrinx application using Django's test client and pytest.

## Overview

Integration tests verify complete user workflows through the UI, ensuring all components work together correctly. They use Django's test client to simulate HTTP requests and responses, testing the full stack from URLs to views to models.

## Test Structure

Integration tests follow these conventions:

1. **File naming**: Use `test_integration_*.py` for integration test files
2. **Function naming**: Use descriptive names that explain the workflow being tested
3. **Decorators**: Always use `@pytest.mark.django_db` for tests that access the database

## Basic Pattern

```python
@pytest.mark.django_db
def test_user_workflow(client, user, other_fixtures):
    """Test description of what workflow is being tested."""
    # 1. Login user if authentication is required
    client.force_login(user)
    
    # 2. Make GET request to view page
    response = client.get(reverse("app:view-name", args=[obj.id]))
    assert response.status_code == 200
    assert "Expected content" in response.content.decode()
    
    # 3. Make POST request to submit form
    response = client.post(
        reverse("app:action-name", args=[obj.id]),
        {
            "field1": "value1",
            "field2": "value2",
        }
    )
    assert response.status_code == 302  # Redirect after success
    
    # 4. Verify database changes
    obj.refresh_from_db()
    assert obj.field1 == "value1"
    
    # 5. Verify UI reflects changes
    response = client.get(reverse("app:view-name", args=[obj.id]))
    assert "value1" in response.content.decode()
```

## Available Fixtures

The project provides several fixtures in `conftest.py`:

- `client`: Django test client for making HTTP requests
- `user`: A test user instance
- `make_user`: Factory for creating users
- `content_house`: A ContentHouse instance
- `make_content_house`: Factory for creating houses
- `content_fighter`: A ContentFighter instance
- `make_content_fighter`: Factory for creating fighters
- `make_list`: Factory for creating lists
- `make_list_fighter`: Factory for creating list fighters
- `make_equipment`: Factory for creating equipment
- `make_weapon_profile`: Factory for creating weapon profiles
- `make_weapon_accessory`: Factory for creating weapon accessories

## Common Test Scenarios

### Testing Authentication

```python
@pytest.mark.django_db
def test_view_requires_login(client, user):
    """Test that view redirects to login for anonymous users."""
    url = reverse("core:protected-view")
    
    # Test anonymous access
    response = client.get(url)
    assert response.status_code == 302
    assert "/accounts/login/" in response.url
    
    # Test authenticated access
    client.force_login(user)
    response = client.get(url)
    assert response.status_code == 200
```

### Testing Form Submissions

```python
@pytest.mark.django_db
def test_form_submission(client, user):
    """Test form validation and processing."""
    client.force_login(user)
    
    # Test invalid form
    response = client.post(
        reverse("core:form-view"),
        {"invalid": "data"}
    )
    assert response.status_code == 200  # Stays on form page
    assert "This field is required" in response.content.decode()
    
    # Test valid form
    response = client.post(
        reverse("core:form-view"),
        {"required_field": "value"}
    )
    assert response.status_code == 302  # Redirects on success
```

### Testing Permissions

```python
@pytest.mark.django_db
def test_ownership_required(client, user, other_user, make_list):
    """Test that only owners can modify their objects."""
    lst = make_list("Test List", owner=other_user)
    
    client.force_login(user)
    response = client.get(reverse("core:list-edit", args=[lst.id]))
    assert response.status_code == 404  # Not found for non-owner
```

### Testing Search and Filtering

```python
@pytest.mark.django_db
def test_search_functionality(client):
    """Test search filters work correctly."""
    # Create test data
    Equipment.objects.create(name="Bolt Pistol", category="Pistols")
    Equipment.objects.create(name="Plasma Gun", category="Special")
    
    # Test search
    response = client.get(reverse("core:equipment-list") + "?search=bolt")
    assert "Bolt Pistol" in response.content.decode()
    assert "Plasma Gun" not in response.content.decode()
    
    # Test filter
    response = client.get(reverse("core:equipment-list") + "?category=Special")
    assert "Plasma Gun" in response.content.decode()
    assert "Bolt Pistol" not in response.content.decode()
```

## Best Practices

1. **Test complete workflows**: Integration tests should cover entire user journeys, not just individual views
2. **Use descriptive assertions**: Check for specific content in responses to ensure the right template and data are rendered
3. **Test error cases**: Verify that invalid inputs are handled gracefully
4. **Clean test data**: Tests should create their own data and not depend on existing database state
5. **Test permissions**: Always verify that unauthorized users cannot access protected resources
6. **Use factories**: Leverage the provided fixture factories to create test data consistently

## Running Integration Tests

Run all integration tests:
```bash
pytest gyrinx/core/tests/test_integration_*.py
```

Run a specific test:
```bash
pytest gyrinx/core/tests/test_integration_core_functionality.py::test_create_list_and_add_fighter
```

Run with verbose output:
```bash
pytest -v gyrinx/core/tests/test_integration_*.py
```

## Debugging Tips

1. **Print response content**: When a test fails, print `response.content.decode()` to see the actual HTML
2. **Check redirects**: Use `response.url` to see where a redirect is going
3. **Examine form errors**: Access `response.context['form'].errors` to see validation errors
4. **Database state**: Use `Model.objects.all()` to verify database changes
5. **Use pdb**: Add `import pdb; pdb.set_trace()` to debug interactively

## Example: Complete Integration Test

Here's a complete example testing the fighter equipment workflow:

```python
@pytest.mark.django_db
def test_fighter_equipment_workflow(client, user, make_list, make_list_fighter, make_equipment):
    """Test complete workflow of managing fighter equipment."""
    # Setup
    lst = make_list("Test Gang")
    fighter = make_list_fighter(lst, "Fighter")
    weapon = make_equipment("Lasgun", category="Basic Weapons", cost=15)
    
    client.force_login(user)
    
    # View fighter equipment page
    response = client.get(reverse("core:fighter-equipment", args=[fighter.id]))
    assert response.status_code == 200
    assert "Lasgun" in response.content.decode()
    assert "15 credits" in response.content.decode()
    
    # Add equipment
    response = client.post(
        reverse("core:fighter-equipment-add", args=[fighter.id]),
        {"equipment": weapon.id}
    )
    assert response.status_code == 302
    
    # Verify equipment was added
    fighter.refresh_from_db()
    assert fighter.equipment.count() == 1
    assert fighter.equipment.first() == weapon
    
    # View fighter detail page
    response = client.get(reverse("core:fighter", args=[fighter.id]))
    assert response.status_code == 200
    assert "Lasgun" in response.content.decode()
    
    # Remove equipment
    assignment = fighter.assignments()[0]
    response = client.post(
        reverse("core:fighter-equipment-remove", args=[fighter.id, assignment.id])
    )
    assert response.status_code == 302
    
    # Verify equipment was removed
    fighter.refresh_from_db()
    assert fighter.equipment.count() == 0
```

This example demonstrates:
- Setting up test data with fixtures
- Making authenticated requests
- Testing multiple related views
- Verifying database changes
- Checking UI updates reflect data changes