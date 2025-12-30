---
description: Analyze a trace file for performance optimization using the trace playbook
arguments:
  - name: trace_file
    description: Path to the trace JSON file (Google Cloud Trace format)
    required: true
---

# Trace Performance Analysis Playbook

Execute the trace performance analysis playbook on the specified trace file.

## Playbook Instructions

@playbooks/trace/instructions.md

## Reference Materials

- Taxonomy: @playbooks/trace/reference/issue-taxonomy.md
- Glossary: @playbooks/trace/reference/glossary.md

## Execution

Analyze the trace file at `$ARGUMENTS` following the playbook methodology.

### Stage 0: Setup (Interactive)

1. **Extract trace ID** from the filename (e.g., `abc123-trace.json` → `abc123`)
   - Use the filename stem (without extension) as the trace ID
   - If filename is just `trace.json`, use first 8 chars of the trace's root span ID

2. **Copy input to namespaced directory:**
   ```bash
   mkdir -p playbooks/trace/input/{trace-id}
   cp $ARGUMENTS playbooks/trace/input/{trace-id}/trace.json
   ```

3. **Create output directory structure:**
   ```bash
   mkdir -p playbooks/trace/output/{trace-id}
   ```

4. Validate the trace file is valid JSON with required span fields

5. Parse trace structure using existing scripts if available:
   ```bash
   python playbooks/trace/scripts/analyze_trace.py $ARGUMENTS
   ```

6. Generate initial files in `playbooks/trace/output/{trace-id}/`:
   - `scope.md` - analysis parameters
   - `trace-summary.md` - trace metadata
   - `operation-index.md` - operation groups listing

### Stage 1: Per-Span-Group Analysis

For each operation group from the index, create:
- `playbooks/trace/output/{trace-id}/groups/{prefix}/profile.md` using template
- `playbooks/trace/output/{trace-id}/groups/{prefix}/bottlenecks.md` using template

Tag all issues with taxonomy from `playbooks/trace/reference/issue-taxonomy.md`.

### Stage 2: Pattern Aggregation

Create aggregation files in `playbooks/trace/output/{trace-id}/aggregation/`:
- `issue-clusters.md`
- `time-attribution.md`
- `n-plus-one-summary.md`
- `prefetch-gaps.md`
- `critical-path.md`

### Stage 3: Impact Synthesis

Create synthesis files:
- `playbooks/trace/output/{trace-id}/opportunities/*.md` for major issues
- `playbooks/trace/output/{trace-id}/synthesis/impact-estimates.md`
- `playbooks/trace/output/{trace-id}/synthesis/priority-matrix.md`
- `playbooks/trace/output/{trace-id}/synthesis/roadmap.md`
- `playbooks/trace/output/{trace-id}/synthesis/code-locations.md`

### Stage 4: Recommendations

Create final outputs in `playbooks/trace/output/{trace-id}/`:
- `SUMMARY.md` - Executive summary
- `recommendations/*.md` - Action cards
- `baseline.md` - Performance baseline
- `learnings.md` - Institutional memory
- `verification-checklist.md`

### Verification

After completing all stages, verify:
```bash
python playbooks/trace/scripts/verify-completion.py --analysis-dir playbooks/trace/output/{trace-id} --verbose
```

## Output

When complete, direct the user to `playbooks/trace/output/{trace-id}/SUMMARY.md` for the executive summary.
