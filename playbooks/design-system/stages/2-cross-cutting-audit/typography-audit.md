# Typography Audit

## Output

`output/audit/typography.md`

## Process

### 1. Extract Every Text Style Combination

From all per-view audits: every unique combination of `font-size`, `font-weight`, `line-height`, `letter-spacing`, `text-transform`. Count frequency.

### 2. Map to Bootstrap's Type Scale

- Which combinations are stock Bootstrap? (`h1`-`h6`, `.fs-1`-`.fs-6`, `.small`, `.lead`)
- Which are the custom `fs-7`?
- Which are entirely custom (e.g., `caps-label`)?

### 3. Identify the Implicit Type Scale

- Sort all font sizes from largest to smallest
- Identify natural clusters (expect 6-10 meaningful steps)
- Note gaps and overlaps

### 4. Produce Consolidation Recommendation

Proposed type scale:

| Scale name | Size | Weight | Line-height | Letter-spacing | Text-transform | Bootstrap class | Custom class needed | Semantic roles |
|-----------|------|--------|-------------|---------------|---------------|----------------|--------------------|----|
