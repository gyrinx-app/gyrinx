---
description: |
  Four analytical lenses for evaluating code quality: pattern unification, abstraction detection,
  boundary analysis, and simplification. Load this skill when doing code review, architecture
  analysis, or refactoring work. Provides structured checklists for identifying issues and
  evaluating code health.
---

# Code Analysis Lenses

Four analytical lenses for systematically evaluating code quality. Apply these lenses to any area of the codebase to identify concrete improvement opportunities.

## Lens 1: Pattern Unification

Find places where the same conceptual operation is done differently in different parts of the codebase. Divergent patterns increase cognitive load, make bugs harder to spot, and make changes harder to propagate.

**What to look for:**
- Views that handle the same HTTP patterns differently (e.g., one uses a mixin, another decorates, another inlines)
- Handler functions that follow different conventions for error handling, validation, or return values
- Templates that solve the same UI problem with different markup patterns
- Form classes that handle similar validation differently
- URL patterns that break naming conventions
- Test patterns that set up similar scenarios differently

**How to investigate:**
- Read 3-5 files that do the same kind of thing (e.g., all "create" views, all "archive" handlers)
- Compare them side-by-side in your analysis
- Identify the best existing pattern (or synthesise one) and show the diff
- Count instances of each variant to determine which is dominant

**Evaluation criteria:**
- Is there one canonical way to do this operation?
- If not, which variant is most common? Most readable? Most correct?
- What is the migration cost from the minority pattern to the majority pattern?

## Lens 2: Abstraction Detection

Identify repeated code that should be extracted into a shared abstraction — but only when the abstraction is clearly earned. Premature abstraction is worse than duplication.

**The rule of three:** Do not create abstractions for one or two uses. Three instances of a pattern is the minimum threshold. The abstraction must be simpler to understand than the inlined versions.

**What to look for:**
- The same 5-10 lines of logic appearing in multiple handlers or views
- Permission checks or ownership validation done inline instead of via a shared utility
- Query patterns (filter chains, annotations, prefetch patterns) duplicated across views
- Template includes that should exist but don't, causing markup duplication
- Form validation logic duplicated between forms
- Error handling boilerplate repeated across similar operations

**The test:** Would a developer reading the code naturally think "this should be a function"? If yes, it's a real abstraction. If you have to explain why it should be extracted, it's probably premature.

**What to avoid:**
- Extracting code that is similar but serves different purposes
- Creating abstractions that require more parameters than the inlined code has lines
- Abstracting over code that is likely to diverge in the future
- Creating utility modules for operations used in only one or two places

## Lens 3: Boundary Analysis

Find places where modules know too much about each other's internals, where implementation details leak across boundaries, or where the dependency graph is tangled.

**What to look for:**
- Views that reach deep into model relationships (e.g., `fighter.list.campaign.owner` chains)
- Handlers that import from other handler sub-packages instead of going through the model layer
- Templates that contain business logic (conditionals based on complex model state)
- Models that expose internal state that should be encapsulated behind a method or property
- Views that duplicate logic from handlers instead of calling them
- Circular or unnecessary import chains between modules
- Functions that accept more context than they need (e.g., taking a whole request when they only need the user)
- Configuration or settings accessed deep in business logic instead of being passed in

**The principle:** Each layer should talk only to its immediate neighbour. Views call handlers. Handlers call models. Models encapsulate data and core logic. Templates receive simple, pre-computed context.

**Severity scale:**
- **High:** Circular dependencies, business logic in templates, views bypassing handlers for writes
- **Medium:** Deep relationship traversal, handlers importing from sibling handler packages
- **Low:** Minor encapsulation opportunities, slightly over-exposed model internals

## Lens 4: Simplification

Find code that is more complex than it needs to be and propose simpler alternatives. Complexity is the primary enemy of maintainability.

**What to look for:**
- Functions longer than ~30 lines (usually doing too many things)
- Deep nesting (>3 levels of indentation)
- Unnecessary indirection (wrapper functions that just call another function)
- Over-engineered abstractions that serve only one use case
- Configuration or parameterisation that is never varied
- Dead code, unused imports, commented-out code
- Overly defensive error handling for conditions that can't occur in practice
- Complex conditional logic that could be simplified with early returns or guard clauses
- Methods that take too many parameters (may indicate the method is doing too much)
- Boolean flags that change function behavior (consider splitting into two functions)
- Try/except blocks that catch too broadly or handle errors identically

**Simplification techniques:**
- **Early returns:** Replace nested if/else with guard clauses at the top
- **Extract method:** Pull a coherent block into a named function
- **Inline trivial wrappers:** If a function just calls another function, remove the wrapper
- **Delete dead code:** If it's unused, remove it completely. Don't comment it out.
- **Collapse layers:** If an abstraction layer is just pass-through, remove it
- **Replace conditionals with polymorphism:** When the same flag is checked in multiple places
- **Use the framework:** Django provides patterns for common operations. Use them instead of reimplementing.

## Applying the Lenses

When reviewing code, apply lenses in this order:

1. **Simplify first** — Remove obvious complexity before looking for patterns. Simpler code reveals patterns more clearly.
2. **Unify patterns** — Once simplified, compare similar code to find divergences.
3. **Detect abstractions** — After unification, repeated patterns may emerge that warrant extraction.
4. **Check boundaries** — Finally, verify that the resulting code respects module boundaries.

For each finding, document:
- **The problem** — What is wrong, with specific file paths and line numbers
- **Why it matters** — The concrete cost (harder to modify, source of bugs, cognitive overhead)
- **The fix** — Concrete code or clear description of the refactoring
- **The scope** — How many files are affected and what the migration path looks like
- **The risk** — What could break and how to verify the change is safe
