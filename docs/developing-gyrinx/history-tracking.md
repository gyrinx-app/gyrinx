# History Tracking

Gyrinx uses django-simple-history to track changes to all models. This provides a comprehensive audit trail of who made what changes and when.

## Overview

All models that inherit from `AppBase` automatically have history tracking enabled. This means:

- Every create, update, and delete operation is recorded
- The user who made the change is tracked (when possible)
- Full historical state is preserved
- Changes can be queried and compared

## Automatic User Tracking

### Web Requests
For changes made through web requests (forms, admin), the user is automatically tracked via the `HistoryRequestMiddleware`.

### Programmatic Changes
For changes made in code (management commands, scripts), you need to explicitly provide the user:

```python
# Using save_with_user (defaults to owner if no user provided)
campaign = Campaign(name="My Campaign", owner=user)
campaign.save_with_user(user=admin_user)

# Using create_with_user (defaults to owner if no user provided)
campaign = Campaign.objects.create_with_user(
    user=admin_user,
    name="My Campaign",
    owner=user
)

# Using bulk operations with history
campaigns = [Campaign(name=f"Campaign {i}", owner=user) for i in range(3)]
Campaign.bulk_create_with_history(campaigns, user=admin_user)
```

## Default User Behavior

When no explicit user is provided, the system uses the object's `owner` as the history user:

```python
# These will use the owner as the history user
campaign = Campaign.objects.create_with_user(
    name="My Campaign",
    owner=user  # This will be used as history user
)

campaign.save_with_user()  # Uses campaign.owner automatically
```

## History Models

Every model with history tracking gets a corresponding historical model:

```python
# Original model
campaign = Campaign.objects.get(id=some_id)

# Access history
history = campaign.history.all()  # All historical records
latest = campaign.history.first()  # Most recent change
oldest = campaign.history.last()   # First record

# History record fields
for record in history:
    print(f"Change type: {record.history_type}")  # +, ~, or -
    print(f"Changed by: {record.history_user}")
    print(f"Changed at: {record.history_date}")
    print(f"Change reason: {record.history_change_reason}")
```

## Querying History

### All History for a Model
```python
# All campaign history across all campaigns
from gyrinx.core.models.campaign import Campaign
all_history = Campaign.history.all()
```

### Recent Changes
```python
# Recent changes across all models
recent_campaigns = Campaign.history.filter(
    history_date__gte=timezone.now() - timedelta(days=7)
)
```

### Changes by User
```python
# All changes made by a specific user
user_changes = Campaign.history.filter(history_user=user)
```

### Comparing Versions
```python
# Get differences between versions
campaign = Campaign.objects.get(id=some_id)
diff = campaign.get_history_diff()  # Compare latest with previous
```

## Bulk Operations

Standard Django bulk operations don't create history records:

```python
# No history created
Campaign.objects.bulk_create([...])
Campaign.objects.filter(...).update(...)
```

Use the history-aware methods instead:

```python
# Creates history records
Campaign.bulk_create_with_history(campaigns, user=user)
Campaign.objects.filter(...).update_with_user(user=user, field=value)
```

## Best Practices

### Management Commands
Always provide a user for history tracking in management commands:

```python
class Command(BaseCommand):
    def handle(self, *args, **options):
        admin_user = User.objects.get(username='admin')

        # Use history-aware methods
        campaign = Campaign.objects.create_with_user(
            user=admin_user,
            name="Generated Campaign",
            owner=some_user
        )
```

### Data Migrations
For data migrations that create or modify records, ensure history is tracked:

```python
def migrate_data(apps, schema_editor):
    Campaign = apps.get_model('core', 'Campaign')
    User = apps.get_model('auth', 'User')

    admin_user = User.objects.get(username='admin')

    for campaign in Campaign.objects.all():
        campaign.save_with_user(user=admin_user)
```

### Testing
History records are created during tests, so account for them:

```python
@pytest.mark.django_db
def test_campaign_history():
    user = User.objects.create_user(username="test", password="test")
    campaign = Campaign.objects.create_with_user(
        user=user,
        name="Test",
        owner=user
    )

    # Check history was created
    history = campaign.history.all()
    assert history.count() == 1
    assert history.first().history_user == user
```

## Performance Considerations

### History Volume
History records accumulate over time. Consider:
- Periodic cleanup of old history records
- Indexing on `history_date` and `history_user`
- Monitoring database size growth

### Query Optimization
- Use `select_related()` when accessing history users
- Filter history queries by date ranges when possible
- Consider pagination for large history sets

## Troubleshooting

### Missing User Information
If `history_user` is `None`:
- Ensure `HistoryRequestMiddleware` is in `MIDDLEWARE` settings
- Use `save_with_user()` or `create_with_user()` for programmatic changes
- Check that the user is authenticated in the request

### Bulk Operations Not Tracked
Standard bulk operations don't trigger signals that create history:
- Use `bulk_create_with_history()` instead of `bulk_create()`
- Use `update_with_user()` instead of `update()`

### History Not Created
If no history records are created:
- Ensure the model inherits from `AppBase`
- Check that `simple_history` is in `INSTALLED_APPS`
- Verify the model has `history = HistoricalRecords()`
