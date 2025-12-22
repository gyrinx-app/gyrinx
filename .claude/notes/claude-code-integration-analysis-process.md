# Claude Code Integration Analysis Process

A systematic process for Claude Code to analyze a codebase and recommend improvements to its Claude Code integration, memory files, and tooling.

---

## Background: Claude Code Memory System

Claude Code uses a **4-tier hierarchical memory system**:

| Tier | Location | Purpose | Shared |
|------|----------|---------|--------|
| Enterprise | System policy location | Org-wide rules | All org users |
| Project | `./CLAUDE.md` or `./.claude/CLAUDE.md` | Team instructions | Via git |
| Project Rules | `./.claude/rules/*.md` | Modular, topic-specific | Via git |
| User | `~/.claude/CLAUDE.md` | Personal prefs | Just you |
| Project Local | `./CLAUDE.local.md` | Personal project prefs | Just you |

**Key capabilities:**
- `@path/to/file` imports in CLAUDE.md files
- Path-specific rules via YAML frontmatter (`paths: src/**/*.ts`)
- Custom commands in `.claude/commands/`
- Project subagents in `.claude/agents/`
- Recursive memory lookup (parent directories included)

---

## Phase 1: Discovery

### 1.1 Inventory Existing Claude Configuration

```
Find and catalog:
├── CLAUDE.md (root)
├── CLAUDE.local.md (root, if exists)
├── .claude/
│   ├── CLAUDE.md
│   ├── rules/*.md
│   ├── commands/*.md
│   ├── agents/*.md (or *.yaml)
│   └── settings.json
├── */CLAUDE.md (subdirectory memories)
└── */CLAUDE.local.md (subdirectory local memories)
```

**Assessment questions:**
- Is the 4-tier system being utilized?
- Are there modular rules, or is everything in one file?
- Are custom commands defined for repetitive tasks?
- Are project-specific subagents defined?
- Are `@imports` used to reference existing docs?

### 1.2 Analyze CLAUDE.md Content Structure

For each CLAUDE.md found, assess:

| Aspect | Good Signs | Red Flags |
|--------|------------|-----------|
| Specificity | "Use 2-space indentation" | "Format code properly" |
| Structure | Bullet points under headers | Wall of text |
| Currency | Matches actual project state | References dead files/commands |
| Focus | Actionable instructions | Philosophical musings |
| Length | Scannable, <500 lines | Overwhelming, >1000 lines |

### 1.3 Map Supporting Documentation

```
Check for docs that could be @imported:
- README.md
- CONTRIBUTING.md
- docs/*.md
- Architecture decision records
- API documentation
- Style guides
```

**Key question:** Is CLAUDE.md duplicating content that should be @imported?

### 1.4 Identify Project Configuration

```
Catalog available tooling:
- Package scripts (npm run X, make X, ./scripts/X)
- CI/CD configuration
- Pre-commit hooks
- Linting/formatting tools
- Test commands
- Build commands
```

---

## Phase 2: Validation

### 2.1 Command Verification

For each command in CLAUDE.md:

1. **Existence check:** Does the script/command exist?
2. **Syntax check:** Is the documented syntax correct?
3. **Execution check:** Does it run without error? (safe commands only)
4. **Prerequisites:** Are dependencies/setup steps documented?

**Common issues to flag:**
- Renamed or removed commands
- Missing environment variables
- Wrong working directory assumptions
- Outdated arguments/flags

### 2.2 Path Verification

For each file path mentioned:

1. **Existence:** Does the file/directory exist?
2. **Accuracy:** Does content match description?
3. **Completeness:** Are there related files not mentioned?

### 2.3 @Import Validation

For each `@path/to/file` reference:

1. **Resolution:** Does the path resolve?
2. **Relevance:** Is the imported content useful?
3. **Depth:** Are imports nested too deeply? (max 5 hops)

### 2.4 Rules Validation

For each `.claude/rules/*.md` file:

1. **Frontmatter:** Is `paths:` glob pattern valid?
2. **Scope:** Does the rule apply to files that exist?
3. **Consistency:** Do rules conflict with each other?

---

## Phase 3: Gap Analysis

### 3.1 Essential Content Audit

Check if CLAUDE.md covers these areas:

| Section | Priority | Example Content |
|---------|----------|-----------------|
| Quick Commands | Critical | Build, test, lint, format commands |
| Architecture Overview | High | "Django app with core/ and content/ modules" |
| Key Abstractions | High | Main models, services, patterns |
| File Locations | High | Where views, models, templates live |
| Coding Patterns | High | "Use `@pytest.mark.django_db` for tests" |
| Naming Conventions | Medium | File naming, function naming, branch naming |
| Security Considerations | Medium | Input validation, auth patterns |
| What NOT to Do | Medium | Anti-patterns, common mistakes |
| Deployment | Low | How code reaches production |

### 3.2 Modular Rules Opportunity

Identify if `.claude/rules/` would help:

**Good candidates for separate rule files:**
- Language-specific patterns (e.g., `typescript.md`, `python.md`)
- Domain-specific rules (e.g., `api.md`, `database.md`)
- Component-specific rules (e.g., `react-components.md`)
- Security rules (e.g., `security.md`)
- Testing conventions (e.g., `testing.md`)

**Path-specific rule opportunities:**
```yaml
# Example: .claude/rules/api.md
---
paths: src/api/**/*.py
---
# API Development Rules
- All endpoints must validate input
- Use standard error response format
```

### 3.3 Custom Command Opportunities

Identify repetitive prompts that should be commands:

| Pattern | Command Candidate |
|---------|-------------------|
| "Run tests and fix failures" | `/test-fix` |
| "Create a PR for this branch" | `/pr` |
| "Review this code for security" | `/security-review` |
| "Explain this file" | `/explain` |
| "Find and fix issue #X" | `/fix-issue` |

**Command structure:**
```markdown
# .claude/commands/test-fix.md
Run the test suite and fix any failures:
1. Run `pytest -x` to find first failure
2. Analyze the failure
3. Fix the issue
4. Re-run tests to confirm
5. Repeat until all tests pass
```

### 3.4 Subagent Opportunities

Identify specialized workflows that warrant subagents:

| Workflow | Subagent Candidate |
|----------|-------------------|
| Database migrations | `migration-helper` |
| PR reviews | `code-reviewer` |
| Performance analysis | `performance-analyzer` |
| Security auditing | `security-auditor` |
| Documentation | `docs-writer` |

**Subagent structure:**
```yaml
# .claude/agents/migration-helper.yaml
name: migration-helper
description: Helps create and review Django migrations
tools: [Read, Write, Bash, Glob, Grep]
prompt: |
  You are a Django migration specialist. When helping with migrations:
  1. Check existing migrations for conflicts
  2. Validate model changes
  3. Generate migration with descriptive name
  4. Review for data safety
```

### 3.5 @Import Opportunities

Identify content that should use @imports:

```markdown
# Instead of duplicating README content:
See @README.md for project overview.

# Instead of copying API docs:
API patterns documented in @docs/api.md

# Reference package.json for npm scripts:
Available commands in @package.json
```

### 3.6 Subdirectory Memory Opportunities

Identify complex areas needing their own CLAUDE.md:

**Good candidates:**
- Complex modules with unique patterns
- Areas with different tech stacks
- Generated code directories
- Test directories with specific conventions

---

## Phase 4: Quality Assessment

### 4.1 Specificity Score

Rate each instruction:

| Score | Example |
|-------|---------|
| 5 - Excellent | "Run `pytest -n auto --reuse-db` for fast parallel tests" |
| 4 - Good | "Use pytest with parallel workers for testing" |
| 3 - Okay | "Run pytest for testing" |
| 2 - Vague | "Test the code before committing" |
| 1 - Useless | "Make sure it works" |

### 4.2 Actionability Check

For each instruction, ask:
- Can Claude act on this immediately?
- Is the command/pattern concrete?
- Are edge cases addressed?

### 4.3 Maintenance Burden Assessment

Identify instructions likely to become stale:
- Hardcoded version numbers
- Specific file line references
- Team member names
- Absolute paths
- Date-specific information

---

## Phase 5: Recommendations

### 5.1 Categorize Findings

| Category | Criteria | Examples |
|----------|----------|----------|
| **Critical** | Incorrect info, broken commands | Dead command, wrong path |
| **High Value** | Missing essentials, major gaps | No test command, no architecture |
| **Quick Win** | Easy fixes, high impact | Add missing command, fix typo |
| **Enhancement** | Would improve experience | Add custom command, create rule |
| **Low Priority** | Nice to have | Additional examples, edge cases |

### 5.2 Recommendation Template

```markdown
## [Short Title]

**Category:** Critical / High Value / Quick Win / Enhancement / Low Priority
**Location:** File path or "New file"
**Effort:** Minutes / Hour / Hours

### Problem
[What's wrong or missing]

### Impact
[How this affects Claude's effectiveness]

### Recommendation
[Specific action - be concrete]

### Implementation
[Exact content to add/change]
```

### 5.3 Prioritization Matrix

```
                    High Impact
                         │
         Quick Wins      │      Strategic
         (Do First)      │      (Plan These)
                         │
    Low Effort ──────────┼────────── High Effort
                         │
         Skip These      │      Nice to Have
         (Maybe Later)   │      (If Time)
                         │
                    Low Impact
```

---

## Phase 6: Report Structure

```markdown
# Claude Code Integration Analysis: [Project Name]

## Summary
- Memory files found: X
- Commands documented: Y
- Custom commands: Z
- Subagents defined: N
- Critical issues: A
- Quick wins available: B

## Current Configuration
[Table of existing files and their status]

## Critical Issues
[Must fix - incorrect or broken]

## Quick Wins
[Easy improvements with high value]

## Recommended Structure
[Proposed .claude/ directory layout]

## Suggested Additions

### New Rules Files
[Specific .claude/rules/*.md files to create]

### New Commands
[Specific .claude/commands/*.md files to create]

### New Subagents
[Specific .claude/agents/*.yaml files to create]

### CLAUDE.md Updates
[Specific content to add/modify/remove]

## Implementation Order
1. [First priority]
2. [Second priority]
...
```

---

## Execution Checklist

```
Discovery
□ Find all CLAUDE.md and CLAUDE.local.md files
□ Inventory .claude/ directory contents
□ Map @imports and their targets
□ Catalog available commands/scripts
□ Identify related documentation

Validation
□ Test all documented commands
□ Verify all file paths
□ Check @import resolution
□ Validate rule file frontmatter

Gap Analysis
□ Audit essential content coverage
□ Identify modular rule opportunities
□ Identify custom command opportunities
□ Identify subagent opportunities
□ Find @import opportunities
□ Find subdirectory memory needs

Quality Assessment
□ Score instruction specificity
□ Check actionability
□ Assess maintenance burden

Recommendations
□ Categorize all findings
□ Prioritize by impact/effort
□ Write actionable recommendations
□ Propose implementation order
```

---

## Anti-Patterns to Avoid

1. **Don't over-modularize** - Not every rule needs its own file
2. **Don't duplicate** - Use @imports for existing documentation
3. **Don't be vague** - "Follow best practices" helps no one
4. **Don't over-specify** - Details that change often become stale
5. **Don't nest too deep** - Max 5 @import hops for a reason
6. **Don't create unused commands** - Only automate actual repetitive tasks
7. **Don't forget security** - Always include security-relevant rules
8. **Don't ignore existing patterns** - Work with the project's conventions

---

## Success Criteria

A well-integrated project enables Claude to:

1. ✓ Run build/test/lint commands without asking
2. ✓ Follow project conventions automatically
3. ✓ Know where to find and place code
4. ✓ Understand the architecture
5. ✓ Avoid security anti-patterns
6. ✓ Use project-specific workflows via commands
7. ✓ Get context-appropriate rules for different file types
8. ✓ Know what NOT to do
