# Gyrinx threat model

| Metadata | Value |
| --- | --- |
| Baseline | 2026-11-07; origin/main revision 162be7c8b plus controls marked as verification pending |
| Scope | N23 and N26 Django requests, identity, content authoring, media, background tasks, integrations, and deployment |
| Method | Data flows and trust boundaries → assets and adversaries → STRIDE threats → residual risk ratings |
| Evidence | Repository code and linked operational documentation; the live GCS overwrite setting and held-sheet reference counts were checked read-only, while bucket IAM and other runtime controls remain unverified |
| Maintenance | [Review process](process.md): at least quarterly and when a boundary, privilege, storage destination, task handler, incident or deployment path changes |
| Next scheduled review | 2027-02-07 |

## Summary

Gyrinx's highest-priority open concerns are the MFA boundary around N26 staff authoring, held CSV integrity, and renewed overload of public read pages. This branch gives new held CSVs unpredictable object keys and protects legacy shared keys during cleanup; deployment verification is still required, and the files remain in storage documented as public. The model distinguishes observed code behaviour from production configuration that still needs checking.

## Read the model

- [Data flows and trust boundaries](data-flows/index.md) — eight Mermaid sequence diagrams.
- [Assets](assets/index.md) — data and authority worth protecting.
- [Adversaries](adversaries/index.md) — plausible starting access and capabilities.
- [STRIDE threats](threats/index.md) — one file per material scenario.
- [Risk assessment](risk-assessment/index.md) — likelihood, impact, priority, treatment and screening decisions.
- [Review and archive process](process.md) — how to re-rate, verify, close and reopen records.
- [Record templates](templates/index.md) — format for later updates.

For vulnerability reporting, use the [security policy](../../SECURITY.md). The older [Bandit baseline](../security-baseline.md) tracks static-analysis findings rather than these architectural risks.
