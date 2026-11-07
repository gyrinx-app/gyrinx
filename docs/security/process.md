# Maintaining the threat model

| Metadata | Value |
| --- | --- |
| Owner | Repository maintainers, with the component owner named in each risk record |
| Review cadence | At least quarterly and when a trigger below occurs |
| Baseline review | 2026-11-07 |
| Next scheduled review | 2027-02-07 |
| Records | [Flows](data-flows/index.md), [assets](assets/index.md), [adversaries](adversaries/index.md), [threats](threats/index.md), and [risks](risk-assessment/index.md) |

The model records code-supported controls and remaining risk, with deployment uncertainty stated separately. A merged fix is evidence of progress, not proof that a production threat is closed. Keep a record active while deployment, configuration, historical data, or residual exposure still needs checking.

## When to review

Review the affected flows whenever an entry point, privilege, data store, external integration, task handler, or deployment boundary changes. Also review after a relevant incident, new vulnerability, control failure, or material change in production configuration. The quarterly review checks the full [STRIDE coverage table](threats/index.md) and the status of every open or accepted risk, even if no code changed.

## Update a record

1. Trace the changed data and authority across the [boundary list](data-flows/index.md). Check all six STRIDE categories for affected flows. Add a threat only when it has a distinct, material harm or mitigation; record consolidation in the [risk index](risk-assessment/index.md).
2. Update the threat and risk in the same PR as the fix or finding. Preserve their IDs, explain what is observed versus inferred, and link code, tests, incident evidence, the tracking issue or PR, and the responsible component. Record the review date and the next review date or trigger.
3. Reassess likelihood, impact, priority, and confidence after each material control change. An accepted risk stays in the active index with its decision owner, reason, and review date. Do not silently lower a rating because work is planned; label any rating that assumes a fix in a PR as "after fix" until deployment is verified.
4. Keep raw credentials, session material, personal data, and details of an unmitigated live exploit out of public records. Follow the [security policy](../../SECURITY.md) for private reporting and incident response. Add a safe public summary after the immediate exposure is contained.

| State | Meaning | Where it lives |
| --- | --- | --- |
| Active | Material exposure or control-sensitive scenario remains | Active threat and risk indexes |
| Mitigation in progress | A fix is planned or being implemented | Active indexes; link the issue or PR |
| Verification pending | A code fix exists in a PR or a control is configured, but deployment, effectiveness, or historical exposure is not checked | Active indexes |
| Accepted | An owner explicitly accepts the residual risk for a dated period | Active indexes; record decision and next review |
| Archived | Closure evidence is complete and no independent material exposure remains | [Threat archive](threats/archive/index.md) and, when fully closed, [risk archive](risk-assessment/archive/index.md) |

## Close, archive, or reopen

Before archiving, verify the fix in tests and the deployed system, check relevant configuration and historical data, and state any residual risk. Record the deployment or decision date, evidence, owner, and a trigger that would reopen the threat. A code change in this PR alone does not meet that bar: [T-03](threats/t-03-active-upload.md) and [T-05](threats/t-05-task-sender-spoofing.md) remain active until their deployment and residual checks are complete.

Move the full threat record to `threats/archive/` with its ID and history. Leave a short pointer at the old path for existing external links, remove the record from the active index and STRIDE table, and add it to the archive index. Archive its risk record only when every linked material threat is closed; otherwise keep the risk active and link to the archived threat. Update relative links, run `npm run lint:markdown` and `npm run lint:mermaid`, and check the rendered PR. The Mermaid parser runs in pre-commit and CI for security-doc changes. Reopening reverses the move with the same ID and history, then re-rates the risk.

The [threat](templates/threat.md) and [risk](templates/risk.md) templates include review and closure fields. Their change history is a brief decision log, not a copy of PR discussion.
