# Stage 0: Setup

**Mode:** Interactive (requires user input)
**Duration:** 5-10 minutes

## Purpose

Validate the trace file, parse its structure, and establish the analysis scope before autonomous execution.

## Prerequisites

- Trace file(s) in Google Cloud Trace JSON format
- Python environment available for running analysis scripts

## Tasks

### 1. Trace Validation

Verify the trace file is valid and contains expected data:

```bash
# Check file exists and is valid JSON
python -c "import json; json.load(open('TRACE_FILE.json'))"
```

**Validation Criteria:**

- File is valid JSON
- Contains `spans` array
- Each span has: `spanId`, `name`, `startTime`, `endTime`

### 2. Parse Trace Structure

Run the trace parser to extract:

- Total span count
- Unique operation names
- Trace duration
- Root span identification

**Output:** `output/{trace-id}/trace-summary.md`

### 3. Establish Scope

Create scope document with user input:

- Analysis mode (single trace, comparison, batch)
- Focus areas (all operations, specific operations)
- Comparison baseline (if applicable)
- Performance thresholds for concern

**Output:** `output/{trace-id}/scope.md`

### 4. Generate Operation Index

Create index of all unique operations for Stage 1:

- Group by operation prefix (list_, listfighter_, etc.)
- Calculate frequency and total time per operation type
- Identify top N operations for deep analysis

**Output:** `output/{trace-id}/operation-index.md`

## Exit Criteria

- [ ] Trace file validated
- [ ] `output/{trace-id}/trace-summary.md` created
- [ ] `output/{trace-id}/scope.md` created with user confirmation
- [ ] `output/{trace-id}/operation-index.md` created
- [ ] Operation groups identified for Stage 1

## Next Stage

Proceed to Stage 1 (Per-Span-Group Analysis) once all exit criteria met.
