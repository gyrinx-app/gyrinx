---
description: |
  Use this skill when the user mentions "trace playbook", "analyze trace", "performance trace analysis",
  "OTel trace", "OpenTelemetry trace", or asks to analyze a trace file for performance optimization.
  This skill guides systematic analysis of Google Cloud Trace JSON exports to identify bottlenecks,
  N+1 patterns, and generate optimization recommendations.
---

# Trace Performance Analysis

You are helping analyze OpenTelemetry/Google Cloud Trace files for performance optimization.

## Playbook Context

@playbooks/trace/instructions.md

## When to Use

This skill applies when:
- User wants to analyze a trace file for performance issues
- User mentions "trace playbook" or similar
- User has a `.json` trace file from Google Cloud Trace
- User wants to compare before/after traces
- User asks about N+1 queries, slow operations, or performance bottlenecks in a trace

## How to Execute

1. **Load the playbook instructions** from `playbooks/trace/instructions.md`
2. **Follow the stage-by-stage workflow:**
   - Stage 0: Setup (interactive) - validate trace, establish scope
   - Stage 1: Per-Group Analysis (parallel) - analyze each operation group
   - Stage 2: Aggregation - cluster patterns across groups
   - Stage 3: Synthesis - impact analysis and prioritization
   - Stage 4: Recommendations - generate actionable outputs

3. **Use the provided templates** in `playbooks/trace/templates/` for consistent output
4. **Tag issues** using `playbooks/trace/reference/issue-taxonomy.md`
5. **Verify completion** with `python playbooks/trace/scripts/verify-completion.py`

## Key Resources

| Resource | Path | Purpose |
|----------|------|---------|
| Master instructions | `playbooks/trace/instructions.md` | Orchestration guide |
| Issue taxonomy | `playbooks/trace/reference/issue-taxonomy.md` | Classification tags |
| Glossary | `playbooks/trace/reference/glossary.md` | Term definitions |
| Templates | `playbooks/trace/templates/*.md` | Output formats |

## Example Interactions

**User:** "Analyze the trace file trace.json using the trace playbook"
**Action:** Execute full playbook workflow, creating namespaced output directory

**User:** "Compare these two traces before.json and after.json"
**Action:** Run playbook on both, then create comparison analysis

**User:** "What N+1 patterns are in this trace?"
**Action:** Focus on Stage 1-2 to identify and aggregate N+1 patterns

## Output Location

All analysis outputs go to `playbooks/trace/output/{trace-id}/`:
- `SUMMARY.md` - Start here for executive summary
- `groups/` - Per-operation analysis
- `aggregation/` - Pattern clusters
- `recommendations/` - Action cards

Input traces are archived to `playbooks/trace/input/{trace-id}/trace.json`
