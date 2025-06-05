# Group-Based Feature Toggles

Group-based feature toggles allow developers to show or hide features based on a user's membership in Django groups. This system is used for alpha/beta testing, gradual rollouts, and access control.

## Implementation

The feature toggle system uses a custom Django template filter that checks group membership.

### Template Tag

The `in_group` filter is defined in `core/templatetags/group_tags.py`:

```python
@register.filter
def in_group(user, group_name):
    """Check if a user is in a specific group by name."""
    if not user or not user.is_authenticated:
        return False

    try:
        group = Group.objects.get(name=group_name)
        return user.groups.filter(pk=group.pk).exists()
    except Group.DoesNotExist:
        return False
```

### Usage in Templates

Load the template tag library:

```django
{% load group_tags %}
```

Check group membership:

```django
{% if user|in_group:"Campaigns Alpha" %}
    <!-- Content only visible to group members -->
{% endif %}
```

## Examples

### Navigation Items

```django
{% if user|in_group:"Campaigns Alpha" %}
    <li class="nav-item">
        <a class="nav-link {% active_view 'core:campaigns' %}"
           href="{% url 'core:campaigns' %}">Campaigns</a>
    </li>
{% endif %}
```

### Feature Sections

```django
{% if user|in_group:"Beta Features" %}
    <div class="card">
        <h2>Beta Features</h2>
        <!-- Beta content -->
    </div>
{% endif %}
```

### Conditional Elements

```django
{% if user|in_group:"Premium Users" %}
    <button class="btn btn-primary">Advanced Export</button>
{% else %}
    <button class="btn btn-secondary" disabled>
        Advanced Export (Premium Only)
    </button>
{% endif %}
```

## Managing Groups

### Creating Groups

Via Django Admin:
1. Navigate to `/admin/auth/group/`
2. Click "Add Group"
3. Enter group name
4. Save

Via Django Shell:
```python
from django.contrib.auth.models import Group
Group.objects.create(name="Feature Group Name")
```

Via Data Migration:
```python
def create_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.create(name="Campaigns Alpha")
```

### Adding Users to Groups

Via Django Admin:
1. Navigate to user's detail page
2. Select groups in "Groups" field
3. Save

Via Django Shell:
```python
from django.contrib.auth.models import User, Group
user = User.objects.get(username="username")
group = Group.objects.get(name="Campaigns Alpha")
user.groups.add(group)
```

## Testing

Test group membership in unit tests:

```python
def test_feature_visible_to_group_members(self):
    user = User.objects.create_user(username="test")
    group = Group.objects.create(name="Test Feature")
    user.groups.add(group)

    response = self.client.get('/feature-url/')
    self.assertContains(response, "Feature Content")
```

## Current Feature Groups

| Group Name | Purpose | Features |
|------------|---------|----------|
| Campaigns Alpha | Early access to campaign features | Campaign navigation link, campaign creation |

## Best Practices

1. **Descriptive Names**: Use clear group names like "Campaigns Alpha", "Beta Testers"
2. **Document Groups**: Maintain a list of active groups and their purposes
3. **Fail Safe**: The filter returns `False` for non-existent groups
4. **Clean Up**: Remove groups after features are fully released
5. **Test Coverage**: Include tests for both group members and non-members

## Security Considerations

- Group membership is checked server-side
- Template filter prevents rendering, not just hiding with CSS
- Groups should not be used for critical security permissions
- Use Django's permission system for access control

## Performance

The `in_group` filter:
- Makes one database query per check
- Results are not cached by default
- Consider using `select_related('groups')` for user queries if checking many groups
