# Gyrinx threat model

| Metadata | Value |
| --- | --- |
| Baseline | 2026-11-07; origin/main revision bdce46108 plus fixes in this PR |
| Scope | N23 and N26 Django requests, identity, content authoring, media, background tasks, integrations, and deployment |
| Method | Data flows and trust boundaries → assets and adversaries → STRIDE threats → residual risk ratings |
| Evidence | Repository code and linked operational documentation; live cloud IAM, storage policy and runtime variables are unverified |
| Maintenance | Revisit when a boundary, privileged role, storage destination, task handler or deployment path changes |

## Summary

Gyrinx's highest-priority open concerns are the MFA boundary around N26 staff authoring, held CSV integrity, and renewed overload of public read pages. Held authoring CSVs use storage documented as public and fixed object names that can collide across staff authors. The PR closes the player SVG upload path and requires an exact Pub/Sub task sender. The model distinguishes observed code behavior from production configuration that still needs checking.

## Read the model

- [Data flows and trust boundaries](data-flows/index.md) — eight Mermaid sequence diagrams.
- [Assets](assets/index.md) — data and authority worth protecting.
- [Adversaries](adversaries/index.md) — plausible starting access and capabilities.
- [STRIDE threats](threats/index.md) — one file per material scenario.
- [Risk assessment](risk-assessment/index.md) — likelihood, impact, priority, treatment and screening decisions.
- [Record templates](templates/index.md) — format for later updates.

For vulnerability reporting, use the [security policy](../../SECURITY.md). The older [Bandit baseline](../security-baseline.md) tracks static-analysis findings rather than these architectural risks.
