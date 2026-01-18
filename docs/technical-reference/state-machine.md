# State Machine Reference

This reference documents the `StateMachine` descriptor for managing model state transitions with audit history.

## Overview

The `StateMachine` descriptor provides:

- **State validation**: Enforces allowed state transitions at runtime
- **Per-model transition tables**: Each model gets its own `<ModelName>StateTransition` table
- **Transition history**: All state changes are recorded with timestamps and metadata
- **Namespaced API**: All state operations accessed via `instance.states.*`

## Basic Usage

### Defining a State Machine

```python
from gyrinx.core.models.state_machine import StateMachine
from gyrinx.models import Base

class Order(Base):
    states = StateMachine(
        states=[
            ("PENDING", "Pending"),
            ("CONFIRMED", "Confirmed"),
            ("SHIPPED", "Shipped"),
            ("DELIVERED", "Delivered"),
            ("CANCELLED", "Cancelled"),
        ],
        initial="PENDING",
        transitions={
            "PENDING": ["CONFIRMED", "CANCELLED"],
            "CONFIRMED": ["SHIPPED", "CANCELLED"],
            "SHIPPED": ["DELIVERED"],
        },
    )
```

This creates:

1. A `status` CharField on the model with the defined choices
2. An `OrderStateTransition` model for recording transition history
3. A `states` accessor for all state operations

### Transitioning States

```python
order = Order.objects.create()
print(order.status)        # "PENDING"
print(order.states.current) # "PENDING"

# Transition to a new state
order.states.transition_to("CONFIRMED")
print(order.status)  # "CONFIRMED"

# With metadata
order.states.transition_to("SHIPPED", metadata={"carrier": "DHL", "tracking": "12345"})
```

### Checking Transitions

```python
# Check if a transition is allowed
order.states.can_transition_to("SHIPPED")  # True if valid

# Get all valid transitions from current state
order.states.get_valid_transitions()  # ["SHIPPED", "CANCELLED"]

# Check if in terminal state (no outbound transitions)
order.states.is_terminal  # True for "DELIVERED" or "CANCELLED"
```

### Viewing History

```python
# Get all transitions for this instance
for transition in order.states.history:
    print(f"{transition.from_status} -> {transition.to_status}")
    print(f"  at: {transition.transitioned_at}")
    print(f"  metadata: {transition.metadata}")

# Get most recent transition
latest = order.states.history.first()

# Count transitions
order.states.history.count()
```

## API Reference

### StateMachine Constructor

```python
StateMachine(
    states: list[tuple[str, str]],  # (value, label) pairs
    initial: str,                    # Initial state value
    transitions: dict[str, list[str]], # Allowed transitions
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `states` | `list[tuple[str, str]]` | List of (value, label) tuples defining valid states |
| `initial` | `str` | The initial state for new instances |
| `transitions` | `dict[str, list[str]]` | Map of from_state to list of allowed to_states |

### StateMachineAccessor Properties

Accessed via `instance.states`:

| Property | Type | Description |
|----------|------|-------------|
| `current` | `str` | Current status value |
| `display` | `str` | Human-readable label for current status |
| `is_terminal` | `bool` | True if no valid transitions from current state |
| `history` | `QuerySet` | Transitions for this instance, ordered by most recent first |

### StateMachineAccessor Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `can_transition_to(state)` | `bool` | Check if transition is allowed |
| `get_valid_transitions()` | `list[str]` | Get list of valid target states |
| `transition_to(state, metadata=None, save=True)` | `Transition` | Execute transition |

### transition_to Parameters

```python
transition_to(
    new_status: str,
    metadata: dict | None = None,
    save: bool = True,
) -> Transition
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `new_status` | `str` | Required | Target state to transition to |
| `metadata` | `dict` | `None` | Optional metadata to store with transition |
| `save` | `bool` | `True` | Whether to save the model after transitioning |

When `save=False`, the status is updated in memory but not persisted to the model. However, **the transition record is still created in the database**. This is useful when you need to update multiple fields atomically, but you must wrap the entire operation in `transaction.atomic()` to ensure consistency (see Patterns section below).

### Transition Model Fields

The dynamically created transition model (e.g., `OrderStateTransition`) has:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `UUID` | Primary key |
| `instance` | `ForeignKey` | Reference to the parent model |
| `from_status` | `CharField` | Previous status value |
| `to_status` | `CharField` | New status value |
| `transitioned_at` | `DateTimeField` | When the transition occurred |
| `metadata` | `JSONField` | Optional metadata (empty dict by default) |

## Exceptions

### InvalidStateTransition

Raised when attempting an invalid transition:

```python
from gyrinx.core.models.state_machine import InvalidStateTransition

try:
    order.states.transition_to("DELIVERED")  # Invalid from PENDING
except InvalidStateTransition as e:
    print(e.from_status)  # "PENDING"
    print(e.to_status)    # "DELIVERED"
    print(e.allowed)      # ["CONFIRMED", "CANCELLED"]
```

## Configuration Validation

The `StateMachine` validates configuration at creation time:

```python
# Invalid initial state raises ValueError
StateMachine(
    states=[("A", "A"), ("B", "B")],
    initial="INVALID",  # ValueError: Initial state 'INVALID' not found in states
    transitions={},
)

# Invalid transition source raises ValueError
StateMachine(
    states=[("A", "A"), ("B", "B")],
    initial="A",
    transitions={"INVALID": ["B"]},  # ValueError: Transition source 'INVALID' not in states
)

# Invalid transition target raises ValueError
StateMachine(
    states=[("A", "A"), ("B", "B")],
    initial="A",
    transitions={"A": ["INVALID"]},  # ValueError: Transition target 'INVALID' not in states
)
```

## Patterns

### Convenience Methods with Atomic Transactions

For complex state transitions with side effects, create convenience methods wrapped in `transaction.atomic()` to ensure the transition record and model save succeed or fail together:

```python
from django.db import models, transaction

class TaskExecution(Base):
    states = StateMachine(
        states=[
            ("READY", "Ready"),
            ("RUNNING", "Running"),
            ("SUCCESSFUL", "Successful"),
            ("FAILED", "Failed"),
        ],
        initial="READY",
        transitions={
            "READY": ["RUNNING", "FAILED"],
            "RUNNING": ["SUCCESSFUL", "FAILED"],
        },
    )

    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    error_message = models.TextField(blank=True)

    def mark_running(self, metadata=None):
        """Mark task as running with timestamp."""
        with transaction.atomic():
            self.started_at = timezone.now()
            self.states.transition_to("RUNNING", metadata=metadata, save=False)
            self.save(update_fields=["started_at", "status", "modified"])

    def mark_failed(self, error_message, metadata=None):
        """Mark task as failed with error details."""
        with transaction.atomic():
            self.finished_at = timezone.now()
            self.error_message = error_message
            self.states.transition_to("FAILED", metadata=metadata, save=False)
            self.save(update_fields=["finished_at", "error_message", "status", "modified"])
```

The `transaction.atomic()` ensures that if the `save()` fails, the transition record is also rolled back, maintaining consistency between the model state and transition history.

### Accessing Class-Level Configuration

For introspection, access the descriptor on the class:

```python
# Get state configuration
TaskExecution.states.states     # [("READY", "Ready"), ...]
TaskExecution.states.initial    # "READY"
TaskExecution.states.transitions # {"READY": ["RUNNING", "FAILED"], ...}

# Get the transition model class
TaskExecution.states.transition_model  # TaskExecutionStateTransition
```

## Migrations

When adding a `StateMachine` to a model, run `makemigrations`. Django automatically detects the dynamically created transition model:

```bash
python manage.py makemigrations
```

This creates a migration with:

- `AddField` for the `status` field on the parent model
- `CreateModel` for the `<ModelName>StateTransition` table

## Admin Integration

Register the transition model in the admin for visibility:

```python
from django.contrib import admin
from gyrinx.tasks.models import TaskExecutionStateTransition

@admin.register(TaskExecutionStateTransition)
class TaskExecutionStateTransitionAdmin(admin.ModelAdmin):
    list_display = ["id", "instance", "from_status", "to_status", "transitioned_at"]
    list_filter = ["to_status", "from_status"]
    readonly_fields = ["id", "instance", "from_status", "to_status", "transitioned_at", "metadata"]
```
