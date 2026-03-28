# Component Taxonomy

Classification system for UI components found during the audit.

| Classification | Definition | Action |
|---------------|------------|--------|
| **Canonical** | The dominant, most consistent variant. Appears most frequently and represents the intended design. | Encode in the design system spec as-is. |
| **Acceptable Variant** | Intentionally different from canonical for a good reason (e.g., compact size for tables, danger variant for destructive actions). | Encode as a named variant in the spec. |
| **Drift** | Unintentional deviation. Same intended component but with slightly different classes, spacing, or colours. | Migrate to canonical. |
| **Bespoke** | One-off implementation for a specific view that doesn't fit any standard. | Design decision needed: standardise into a new variant, or accept as an exception. |
| **Anti-pattern** | Incorrect usage that causes UX or accessibility problems. | Fix during migration. |
| **Dead** | Styles or components defined in CSS but not used in any template. | Remove during migration. |

## How to Classify

1. Count frequency of each variant across all views
2. The most frequent variant is the **canonical** candidate
3. Variants with clear, justifiable reasons for being different are **acceptable variants**
4. Variants that look like "the same thing but slightly off" are **drift**
5. One-offs with no clear pattern are **bespoke**
6. Anything causing usability/accessibility issues is an **anti-pattern**
7. CSS rules with no template references are **dead**
