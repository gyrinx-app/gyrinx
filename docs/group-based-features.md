# Group-Based Feature Toggles

This document describes how to use group-based feature toggles in Gyrinx templates.

## Overview

Group-based feature toggles allow you to show or hide features based on a user's membership in specific Django groups. This is useful for:
- Alpha/beta testing features with select users
- Gradual feature rollouts
- Access control for premium features

## Template Tag Usage

### Basic Usage

First, load the `group_tags` in your template:

```django
{% load group_tags %}
```

Then use the `in_group` filter to check membership:

```django
{% if user|in_group:"Group Name" %}
    <!-- Content only visible to group members -->
{% endif %}
```

### Examples

#### Navigation Items
```django
{% if user|in_group:"Campaigns Alpha" %}
    <li class="nav-item">
        <a class="nav-link" href="{% url 'core:campaigns' %}">Campaigns</a>
    </li>
{% endif %}
```

#### Feature Sections
```django
{% if user|in_group:"Beta Testers" %}
    <div class="card">
        <div class="card-header">Beta Features</div>
        <div class="card-body">
            <!-- Beta feature content -->
        </div>
    </div>
{% endif %}
```

#### Conditional Buttons
```django
{% if user|in_group:"Premium Users" %}
    <button class="btn btn-primary">Export to PDF</button>
{% else %}
    <button class="btn btn-secondary" disabled>Export to PDF (Premium)</button>
{% endif %}
```

## How It Works

The `in_group` filter:
1. Checks if the user is authenticated
2. Looks up the group by exact name match
3. Returns `True` if the user is a member, `False` otherwise
4. Returns `False` if the group doesn't exist (fail-safe behavior)

## Creating Groups

Groups can be created via:
1. Django Admin interface: `/admin/auth/group/`
2. Django shell: `Group.objects.create(name="Group Name")`
3. Data migration

## Adding Users to Groups

Users can be added to groups via:
1. Django Admin interface
2. Django shell:
   ```python
   user = User.objects.get(username="username")
   group = Group.objects.get(name="Campaigns Alpha")
   user.groups.add(group)
   ```

## Best Practices

1. **Use descriptive group names**: "Campaigns Alpha", "Beta Testers", "Premium Users"
2. **Document groups**: Keep a list of active feature groups and their purposes
3. **Clean up old groups**: Remove groups for features that have been fully released
4. **Fail gracefully**: The filter returns `False` for non-existent groups, so features stay hidden if groups are deleted
