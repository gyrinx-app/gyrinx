# Risk assessment

| Metadata | Value |
| --- | --- |
| Baseline | 2026-11-07; repository revision bdce46108 plus fixes in this PR |
| Scope | Material application, media, task, and deployment outcomes represented by the threat inventory |
| Rating basis | Residual exposure after controls visible in this branch; deployed cloud policy is unverified unless stated |
| Review trigger | New entry point, storage policy, privileged role, task handler, deployment path, or relevant incident |
| Owner | Maintainers of the named component; operational findings require an infrastructure owner |
| Lifecycle | [Review process](../process.md); [archived assessments](archive/index.md) retain closure decisions |

Likelihood is **low** when a strong control or unusual access is needed, **medium** when a plausible account, leaked URL, or configuration condition is enough, and **high** when the path is readily repeatable from a public boundary. Impact is **low** for local reversible nuisance, **medium** for limited data or service harm, **high** for broad integrity, confidentiality, or availability harm, and **critical** for system-wide execution or credential exposure. Priority considers both dimensions, the strength of existing controls, and the cost of uncertainty. Confidence describes the evidence, not the likelihood.

These are scenario ratings, not measured frequencies. A code-supported conditional risk needs a production configuration check before its likelihood can be firm. A risk with a fix in a PR stays here until deployment and residual exposure are verified.

R-03 and R-05 have code changes in this PR but remain active until deployment and residual checks support [archiving](archive/index.md). Accepted risks also remain active with a named decision owner and next review date.

| ID | Outcome | Likelihood | Impact | Priority | State | Evidence confidence |
| --- | --- | --- | --- | --- | --- | --- |
| [R-01](r-01-staff-mfa.md) | Staff password reaches content publishing without the admin MFA gate | Medium | High | High | Open | High for code path; medium for production exposure |
| [R-02](r-02-authorization.md) | Authorization regression changes or reveals another player's data | Low | High | Medium | Controlled invariant | Medium |
| [R-03](r-03-active-media.md) | Player SVG through TinyMCE reaches the public media origin | Low | Medium | Low | Verification pending | High |
| [R-04](r-04-held-csv.md) | Held authoring CSV is readable through predictable public media URL | Medium | Medium | Medium | Open | High for design; medium for live bucket policy |
| [R-05](r-05-task-sender.md) | Unintended Google principal dispatches an internal task | Low after fix | Critical | Medium | Verification pending | High for code, low for live IAM |
| [R-06](r-06-public-overload.md) | Repeated public reads exhaust serving capacity | Medium | High | High | Residual | High for incident mechanism; medium for current edge policy |
| [R-07](r-07-impersonation-audit.md) | Impersonated action cannot be attributed directly to its operator | Medium | Medium | Medium | Open | Medium |
| [R-08](r-08-deployment.md) | Compromised build or deploy authority changes production code | Low | Critical | High | Needs control validation | Low for deployed IAM, high for code path |
| [R-09](r-09-held-csv-integrity.md) | Held CSV key collision changes or removes another author's source file | Medium | High | High | Open | High for code path; medium for live storage |

## Screening and consolidation

The [threat inventory](../threats/index.md) covers all six STRIDE categories. Each risk above represents a distinct direct harm or control owner. [T-02](../threats/t-02-cross-owner-write.md) and [T-08](../threats/t-08-shared-read-privacy.md) are grouped in R-02 because both depend on preserving object-level authorization across N23 and N26. [T-03](../threats/t-03-active-upload.md) stays active after the upload guard until deployment and historical media are checked. [T-10](../threats/t-10-held-sheet-collision.md) is assessed separately as R-09: a shared storage key can change or remove another author's bytes, and private reads alone would not fix that integrity problem. Generic browser CSRF, direct database administration, and speculative compromise of every dependency are omitted because existing controls or the same larger privileged/deployment risks cover their consequences.

## Highest-value follow-ups

1. Apply the same current-session MFA requirement to N26 staff authoring as to Django admin (R-01).
2. Give held CSV uploads unique object keys and preserve legacy shared objects until no row references them (R-09).
3. Move held ingest files to private storage; verify live bucket IAM and object access first (R-04).
4. Verify the deployed Pub/Sub sender identity, source protection, build/deploy IAM, and edge throughput policy (R-05, R-08, R-06).
