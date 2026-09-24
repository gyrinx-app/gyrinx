---
applyTo: "**/*.py"
---

# Reviewing Python

The runtime is Python 3.14 (`requires-python = ">=3.14"`). Ruff's
`target-version` is `py314`, so the formatter emits 3.14 syntax.

## PEP 758 except groups

`except ValueError, TypeError:` (no parentheses, no `as`) is valid. It is not
Python 2 syntax, not an unused import, and not a SyntaxError. Do not ask to
rewrite it as `except (ValueError, TypeError):` — `ruff format` will strip those
parentheses on the next format.

Parentheses stay required when the clause binds the exception:

```python
except (ValueError, TypeError) as exc:
```

`except ValueError, TypeError as exc:` is still a SyntaxError. Decline only
findings that misread the no-`as` form.

A live example Copilot has already misread: `except Refusal, ValueError:` in
`n26/core/action_initialisation.py`.
