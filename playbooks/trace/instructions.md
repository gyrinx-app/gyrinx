# OpenTelemetry Trace Performance Analysis Playbook

A systematic methodology for analyzing performance traces to identify bottlenecks and generate optimization recommendations.

## Quick Start

```bash
# Run the command with any trace file path:
/trace-playbook path/to/abc123-trace.json

# The playbook will:
# 1. Extract trace ID from filename (e.g., "abc123")
# 2. Copy input to: playbooks/trace/input/abc123/trace.json
# 3. Write output to: playbooks/trace/output/abc123/
```

## Directory Structure

Each trace analysis is namespaced by trace ID:

```
playbooks/trace/
├── input/{trace-id}/          # Archived input traces
│   └── trace.json
├── output/{trace-id}/         # Analysis outputs
│   ├── SUMMARY.md
│   └── ...
```

This allows multiple traces to be analyzed independently.

## Purpose

This playbook guides analysis of Google Cloud Trace JSON exports to:

- Identify performance bottlenecks
- Detect N+1 query patterns
- Find missing prefetch opportunities
- Generate prioritized optimization recommendations
- Establish performance baselines for comparison

## Execution Model

### Analysis Modes

| Mode | Description | When to Use |
|------|-------------|-------------|
| **Single Trace** | Deep-dive one trace | Investigating specific slow request |
| **Comparison** | Before/after analysis | Validating optimization impact |
| **Batch** | Multiple traces | Finding patterns across requests |

### Stage Overview

| Stage | Mode | Purpose | Output |
|-------|------|---------|--------|
| 0 - Setup | Interactive | Validate trace, establish scope | `output/{trace-id}/scope.md` |
| 1 - Per-Group | Parallel | Analyze each operation group | `output/{trace-id}/groups/*/` |
| 2 - Aggregation | Sequential | Cluster patterns | `output/{trace-id}/aggregation/` |
| 3 - Synthesis | Sequential | Impact analysis | `output/{trace-id}/synthesis/` |
| 4 - Recommendations | Sequential | Final outputs | `output/{trace-id}/SUMMARY.md` |

---

## Stage 0: Setup (Interactive)

**Read:** `playbooks/trace/stages/0-setup/README.md`

### Tasks

1. **Extract trace ID and copy input**
   - Extract trace ID from filename (e.g., `abc123-trace.json` → `abc123`)
   - If filename is just `trace.json`, use first 8 chars of root span ID
   - Copy input: `cp {input} playbooks/trace/input/{trace-id}/trace.json`
   - Create output dir: `mkdir -p playbooks/trace/output/{trace-id}`

2. **Validate trace file**
   - Confirm JSON is valid
   - Check for required span fields

3. **Parse trace structure**

   ```bash
   # Use provided analysis scripts or manual inspection
   python playbooks/trace/scripts/analyze_trace.py {input}
   ```

4. **Create scope document**
   - Confirm analysis mode (single/comparison/batch)
   - Set focus areas
   - Record baseline if comparing

5. **Generate operation index**
   - List all unique operation prefixes
   - Calculate frequency and time per group

### Exit Criteria

- [ ] Input copied to `input/{trace-id}/trace.json`
- [ ] `output/{trace-id}/scope.md` created
- [ ] `output/{trace-id}/trace-summary.md` created
- [ ] `output/{trace-id}/operation-index.md` created
- [ ] User confirmed scope

---

## Stage 1: Per-Span-Group Analysis (Parallel)

**Read:** `playbooks/trace/stages/1-per-span-group/README.md`

### Parallelization

For each operation group from the index, launch a sub-agent:

```
Sub-agent prompt for group "{prefix}":

Analyze the '{prefix}' operation group from trace file {path}.

Instructions: playbooks/trace/stages/1-per-span-group/README.md
Templates: playbooks/trace/templates/operation-profile.md, playbooks/trace/templates/bottleneck-analysis.md
Taxonomy: playbooks/trace/reference/issue-taxonomy.md

Create:
1. output/{trace-id}/groups/{prefix}/profile.md
2. output/{trace-id}/groups/{prefix}/bottlenecks.md

Tag all issues using the taxonomy.
```

**Recommended:** 3-5 concurrent agents

### Exit Criteria

- [ ] All groups from index have `profile.md`
- [ ] All groups from index have `bottlenecks.md`
- [ ] All issues tagged with taxonomy

---

## Stage 2: Pattern Aggregation (Sequential)

**Read:** `playbooks/trace/stages/2-pattern-aggregation/README.md`

### Tasks

1. Cluster all issues by type, impact, complexity
2. Create time attribution accounting for 100% of trace
3. Consolidate N+1 patterns
4. Map prefetch gaps
5. Identify critical path

### Exit Criteria

- [ ] `output/{trace-id}/aggregation/issue-clusters.md`
- [ ] `output/{trace-id}/aggregation/time-attribution.md`
- [ ] `output/{trace-id}/aggregation/n-plus-one-summary.md`
- [ ] `output/{trace-id}/aggregation/prefetch-gaps.md`
- [ ] `output/{trace-id}/aggregation/critical-path.md`

---

## Stage 3: Impact Synthesis (Sequential)

**Read:** `playbooks/trace/stages/3-impact-synthesis/README.md`

### Tasks

1. Create opportunity documents for major issues
2. Apply impact estimation framework
3. Build priority matrix
4. Create implementation roadmap
5. Map code locations

### Exit Criteria

- [ ] `output/{trace-id}/opportunities/*.md` for top issues
- [ ] `output/{trace-id}/synthesis/impact-estimates.md`
- [ ] `output/{trace-id}/synthesis/priority-matrix.md`
- [ ] `output/{trace-id}/synthesis/roadmap.md`
- [ ] `output/{trace-id}/synthesis/code-locations.md`

---

## Stage 4: Recommendations (Sequential)

**Read:** `playbooks/trace/stages/4-recommendations/README.md`

### Tasks

1. Create executive summary
2. Write recommendation cards
3. Document performance baseline
4. Capture learnings
5. Create verification checklist

### Exit Criteria

- [ ] `output/{trace-id}/SUMMARY.md`
- [ ] `output/{trace-id}/recommendations/*.md` for top 5 opportunities
- [ ] `output/{trace-id}/baseline.md`
- [ ] `output/{trace-id}/learnings.md`
- [ ] `output/{trace-id}/verification-checklist.md`

---

## Verification

After completing all stages:

```bash
python playbooks/trace/scripts/verify-completion.py --analysis-dir playbooks/trace/output/{trace-id} --verbose
```

Expected output: `COMPLETE: All checks passed`

---

## Reference Documents

| Document | Purpose |
|----------|---------|
| `playbooks/trace/reference/issue-taxonomy.md` | Classification tags for issues |
| `playbooks/trace/reference/glossary.md` | Term and metric definitions |
| `playbooks/trace/templates/*.md` | Output format templates |

---

## Operational Constraints

### File Operations

- Use Write/Read/Edit tools (not shell commands)
- Create analysis directory structure as needed
- Minimum file size: 500 bytes

### Quality Standards

- All issues must be tagged with taxonomy
- All time must be attributed
- All recommendations need confidence levels
- All code locations must be verifiable

### Error Handling

- If trace is invalid, stop at Stage 0
- If operation group fails, log and continue with others
- If aggregation incomplete, note gaps in synthesis

---

## Output Structure

```
playbooks/trace/
├── input/{trace-id}/             # Archived inputs
│   └── trace.json
└── output/{trace-id}/            # Analysis outputs
    ├── SUMMARY.md                # Executive summary (start here)
    ├── scope.md                  # Analysis parameters
    ├── trace-summary.md          # Trace metadata
    ├── operation-index.md        # Operation inventory
    ├── baseline.md               # Performance baseline
    ├── learnings.md              # Institutional memory
    ├── verification-checklist.md # Implementation tracking
    ├── groups/                   # Stage 1: Per-operation
    │   └── {prefix}/
    │       ├── profile.md
    │       └── bottlenecks.md
    ├── aggregation/              # Stage 2: Patterns
    │   ├── issue-clusters.md
    │   ├── time-attribution.md
    │   ├── n-plus-one-summary.md
    │   ├── prefetch-gaps.md
    │   └── critical-path.md
    ├── synthesis/                # Stage 3: Impact
    │   ├── impact-estimates.md
    │   ├── priority-matrix.md
    │   ├── roadmap.md
    │   └── code-locations.md
    ├── opportunities/            # Stage 3: Details
    │   └── {opportunity-name}.md
    └── recommendations/          # Stage 4: Actions
        └── {recommendation-name}.md
```

---

## Example Usage

### Single Trace Analysis

```
User: Analyze the trace at e2b8a97b.json using the playbook

Agent:
1. Reads playbooks/trace/instructions.md
2. Validates trace, creates scope
3. Generates operation index
4. Launches sub-agents for each operation group
5. Aggregates patterns
6. Synthesizes opportunities
7. Generates recommendations
8. Creates SUMMARY.md
```

### Before/After Comparison

```
User: Compare traces before.json and after.json using the playbook

Agent:
1. Analyzes both traces through Stage 3
2. Creates comparison-analysis.md using template
3. Generates attribution analysis
4. Updates recommendations based on what worked
```
