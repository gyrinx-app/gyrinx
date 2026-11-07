import {
    ActionBar,
    Badge,
    Breadcrumbs,
    ButtonLink,
    Card,
    Link,
} from "../../ui";
import { ScheduleEditor } from "./ScheduleEditor";
import type { Credits, Cycle, ScheduleProps } from "./types";

export function creditsText(amount: Credits | undefined) {
    if (!amount) return "0¢";
    const dice = amount.dice;
    const expression = dice
        ? `${dice.count}D${dice.sides}${dice.multiplier !== 1 ? ` × ${dice.multiplier}` : ""}`
        : "";
    return `${expression}${expression && amount.fixed ? " + " : ""}${amount.fixed || !expression ? amount.fixed : ""}¢`;
}
function dateText(value: string) {
    return new Date(`${value}T00:00:00`).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
    });
}
function CycleRow({ cycle, focus }: { cycle: Cycle; focus: boolean }) {
    return (
        <div
            id={`cycle-${cycle.key}`}
            className="rounded-control border border-box-border p-3"
        >
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                        {cycle.href ? (
                            <Link href={cycle.href}>{cycle.name}</Link>
                        ) : (
                            <span className="font-medium">{cycle.name}</span>
                        )}
                        <Badge
                            color={cycle.state === "Current" ? "amber" : "ink"}
                        >
                            {cycle.state}
                        </Badge>
                    </div>
                    <Link href={`#phase-${cycle.phaseId}`} className="text-sm">
                        {cycle.phaseName}
                    </Link>
                    {(cycle.startsOn || cycle.endsOn) && (
                        <p className="text-sm text-muted">
                            Planned:{" "}
                            {cycle.startsOn
                                ? dateText(cycle.startsOn)
                                : "No start date"}
                            {cycle.endsOn
                                ? ` to ${dateText(cycle.endsOn)}`
                                : ""}
                        </p>
                    )}
                </div>
                {cycle.editHref && (
                    <ButtonLink
                        href={cycle.editHref}
                        variant="ghost"
                        size="sm"
                        aria-label={`Edit ${cycle.name}`}
                    >
                        Edit
                    </ButtonLink>
                )}
            </div>
            {cycle.href && (
                <details open={focus || undefined} className="mt-2 text-sm">
                    <summary className="cursor-pointer text-muted">
                        Cycle details
                    </summary>
                    <div className="mt-2 space-y-2">
                        {cycle.description && (
                            <p className="whitespace-pre-wrap">
                                {cycle.description}
                            </p>
                        )}
                        {cycle.effects && (
                            <p className="whitespace-pre-wrap">
                                {cycle.effects}
                            </p>
                        )}
                        {cycle.startedAt && (
                            <p>
                                Started:{" "}
                                {new Date(cycle.startedAt).toLocaleString(
                                    "en-GB",
                                )}
                            </p>
                        )}
                        {cycle.endedAt && (
                            <p>
                                Ended:{" "}
                                {new Date(cycle.endedAt).toLocaleString(
                                    "en-GB",
                                )}
                            </p>
                        )}
                        <Link href={`#phase-${cycle.phaseId}`}>
                            Read the phase rules
                        </Link>
                    </div>
                </details>
            )}
        </div>
    );
}

export function CampaignSchedule(props: ScheduleProps) {
    const names = new Map(props.phases.map((phase) => [phase.id, phase.name]));
    return (
        <div className="space-y-6">
            <Breadcrumbs
                items={[
                    { label: "Campaigns", href: "/n26/campaigns/" },
                    { label: props.campaignName, href: props.campaignHref },
                    { label: "Cycles" },
                ]}
            />
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                    <h1 className="text-2xl font-semibold">Campaign cycles</h1>
                    <p className="text-sm text-muted">{props.status}</p>
                </div>
                {props.actions.transition && (
                    <ButtonLink
                        href={props.actions.transition}
                        variant="primary"
                    >
                        {props.actions.transitionLabel}
                    </ButtonLink>
                )}
            </div>
            {!props.configured ? (
                <Card>
                    <p className="mb-3">
                        {props.canManage
                            ? "Set up phases and cycles for this campaign."
                            : "The arbitrator has not set up campaign cycles."}
                    </p>
                    {props.actions.setup && (
                        <ButtonLink
                            href={props.actions.setup}
                            variant="primary"
                        >
                            Set up cycles
                        </ButtonLink>
                    )}
                </Card>
            ) : (
                <>
                    <Card>
                        <div className="flex flex-wrap items-center gap-2">
                            <Badge>Current</Badge>
                            <strong>{props.currentName}</strong>
                            <span>{props.currentPhase}</span>
                        </div>
                    </Card>
                    <section
                        aria-labelledby="cycle-list-heading"
                        className="space-y-3"
                    >
                        <h2
                            id="cycle-list-heading"
                            className="text-lg font-semibold"
                        >
                            Schedule
                        </h2>
                        <p className="text-sm text-muted">
                            Projected cycles are previews. Editing one or
                            selecting it for a battle saves the preceding
                            projected cycles too.
                        </p>
                        <div className="space-y-2">
                            {props.rows.map((cycle) => (
                                <CycleRow
                                    key={cycle.key}
                                    cycle={cycle}
                                    focus={props.focusId === cycle.key}
                                />
                            ))}
                        </div>
                        <div className="flex flex-wrap gap-3">
                            {props.previousHref && (
                                <Link href={props.previousHref}>
                                    Earlier cycles
                                </Link>
                            )}
                            {props.nextHref && (
                                <Link href={props.nextHref}>
                                    Later saved cycles
                                </Link>
                            )}
                            {props.moreHref && (
                                <Link href={props.moreHref}>
                                    Show more projected cycles
                                </Link>
                            )}
                        </div>
                    </section>
                    {props.plan && (
                        <section
                            aria-labelledby="future-plan-heading"
                            className="space-y-3"
                        >
                            <ActionBar
                                trailing={
                                    props.actions.plan && (
                                        <ButtonLink
                                            href={props.actions.plan}
                                            size="sm"
                                            variant="ghost"
                                        >
                                            Edit future plan
                                        </ButtonLink>
                                    )
                                }
                            >
                                <h2
                                    id="future-plan-heading"
                                    className="font-semibold"
                                >
                                    {props.plan.mode === "repeating"
                                        ? "Repeating pattern"
                                        : "Future plan"}
                                </h2>
                            </ActionBar>
                            <ol className="flex flex-wrap gap-2">
                                {props.plan.steps.map((step, index) => (
                                    <li
                                        key={step.id}
                                        className="rounded-control border border-box-border px-3 py-2 text-sm"
                                    >
                                        <span className="mr-2 text-muted">
                                            {index + 1}.
                                        </span>
                                        {names.get(step.phase_id)} ×{" "}
                                        {step.count}
                                    </li>
                                ))}
                            </ol>
                            {!props.plan.steps.length && (
                                <p className="text-sm text-muted">
                                    The fixed plan has no remaining projected
                                    cycles.
                                </p>
                            )}
                            {props.canManage && (
                                <div className="flex flex-wrap gap-3">
                                    <Link href={props.actions.template}>
                                        Apply a template
                                    </Link>
                                    <Link href={props.actions.saveTemplate}>
                                        Save as a template
                                    </Link>
                                </div>
                            )}
                        </section>
                    )}
                    <section
                        aria-labelledby="phase-rules-heading"
                        className="space-y-3"
                    >
                        <h2
                            id="phase-rules-heading"
                            className="text-lg font-semibold"
                        >
                            Phases and rules
                        </h2>
                        {props.phases.map((phase) => (
                            <div id={`phase-${phase.id}`} key={phase.id}>
                                <Card>
                                    <div className="flex flex-wrap items-start justify-between gap-3">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <h3 className="font-semibold">
                                                {phase.name}
                                            </h3>
                                            {phase.id ===
                                                props.currentPhaseId && (
                                                <Badge>Current phase</Badge>
                                            )}
                                        </div>
                                        {props.canManage && (
                                            <div className="flex flex-wrap gap-3 text-sm">
                                                <Link href={phase.editHref}>
                                                    Edit
                                                </Link>
                                                <Link
                                                    href={phase.duplicateHref}
                                                >
                                                    Duplicate
                                                </Link>
                                                {phase.deleteHref && (
                                                    <Link
                                                        href={phase.deleteHref}
                                                        tone="danger"
                                                    >
                                                        Delete
                                                    </Link>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                    {phase.description && (
                                        <p className="mt-3 whitespace-pre-wrap">
                                            {phase.description}
                                        </p>
                                    )}
                                    {phase.effects && (
                                        <p className="mt-2 whitespace-pre-wrap">
                                            {phase.effects}
                                        </p>
                                    )}
                                    <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                                        {(["win", "draw", "loss"] as const).map(
                                            (outcome) => (
                                                <div key={outcome}>
                                                    <dt className="capitalize text-muted">
                                                        {outcome}
                                                    </dt>
                                                    <dd>
                                                        {creditsText(
                                                            phase.rewards[
                                                                outcome
                                                            ]?.credits,
                                                        )}{" "}
                                                        ·{" "}
                                                        {phase.rewards[outcome]
                                                            ?.reputation ??
                                                            0}{" "}
                                                        reputation
                                                    </dd>
                                                </div>
                                            ),
                                        )}
                                        <div>
                                            <dt className="text-muted">
                                                Phase entry
                                            </dt>
                                            <dd>
                                                {creditsText(
                                                    phase.rewards.entry_credits,
                                                )}
                                            </dd>
                                        </div>
                                    </dl>
                                </Card>
                            </div>
                        ))}
                    </section>
                </>
            )}
            {props.editor && (
                <ScheduleEditor
                    editor={props.editor}
                    phases={props.phases}
                    onNavigate={props.onNavigate}
                    onReload={props.onReload}
                />
            )}
        </div>
    );
}
