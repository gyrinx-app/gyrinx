import {
    ActionBar,
    ActionMenu,
    Badge,
    Breadcrumbs,
    Button,
    ButtonLink,
    Card,
    Icon,
    Link,
    Table,
} from "../../ui";
import { ScheduleEditor } from "./ScheduleEditor";
import { useScheduleNavigation } from "./useScheduleNavigation";
import type { Credits, Cycle, Phase, ScheduleProps } from "./types";

export function creditsText(amount: Credits | undefined) {
    if (!amount) return "0¢";
    const dice = amount.dice;
    const expression = dice
        ? `${dice.count}D${dice.sides}${dice.multiplier !== 1 ? ` × ${dice.multiplier}` : ""}`
        : "";
    return `${expression}${expression && amount.fixed ? " + " : ""}${amount.fixed || !expression ? amount.fixed : ""}¢`;
}

function dateText(value: string) {
    return new Date(
        value.length === 10 ? `${value}T00:00:00` : value,
    ).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "short",
        year: "numeric",
    });
}

function CycleDates({ cycle }: { cycle: Cycle }) {
    const range =
        cycle.startsOn && cycle.endsOn ? (
            <span className="inline-flex items-center gap-1 whitespace-nowrap">
                <span className="sr-only">Start date:</span>
                <time dateTime={cycle.startsOn}>
                    {dateText(cycle.startsOn)}
                </time>
                <span aria-hidden="true">–</span>
                <span className="sr-only">End date:</span>
                <time dateTime={cycle.endsOn}>{dateText(cycle.endsOn)}</time>
            </span>
        ) : (
            "Dates not set"
        );
    if (!cycle.editHref)
        return <span className="text-xs text-muted">{range}</span>;
    const url = new URL(cycle.editHref, window.location.origin);
    url.searchParams.set("fields", "dates");
    return (
        <Link
            href={url.pathname + url.search}
            className="inline-block py-1 text-xs"
            aria-label={`Edit dates for ${cycle.name}: ${cycle.startsOn && cycle.endsOn ? `Start date ${dateText(cycle.startsOn)}, end date ${dateText(cycle.endsOn)}` : "Dates not set"}`}
            title="Edit start and end dates"
        >
            {range}
        </Link>
    );
}

function CycleRow({ cycle }: { cycle: Cycle }) {
    return (
        <tr
            id={`cycle-${cycle.key}`}
            className={cycle.state === "Current" ? "bg-accent/5" : ""}
        >
            <td className="align-top [overflow-wrap:anywhere]">
                <div className="flex items-start gap-2">
                    <span
                        className="mt-0.5 w-5 shrink-0 text-xs tabular-nums text-muted"
                        aria-hidden="true"
                    >
                        {cycle.order.toString().padStart(2, "0")}
                    </span>
                    <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                            <span className="font-medium">{cycle.name}</span>
                            <Badge
                                color={
                                    cycle.state === "Current" ? "amber" : "ink"
                                }
                            >
                                {cycle.state}
                            </Badge>
                        </div>
                        {cycle.description && (
                            <p className="mt-0.5 whitespace-pre-wrap text-sm text-muted">
                                {cycle.description}
                            </p>
                        )}
                        <div className="mt-1 sm:hidden">
                            <CycleDates cycle={cycle} />
                        </div>
                        {(cycle.effects ||
                            cycle.startedAt ||
                            cycle.endedAt) && (
                            <details className="mt-1 text-xs">
                                <summary className="cursor-pointer text-muted">
                                    More details
                                </summary>
                                <div className="mt-1 space-y-1">
                                    {cycle.effects && (
                                        <p className="whitespace-pre-wrap">
                                            {cycle.effects}
                                        </p>
                                    )}
                                    {cycle.startedAt && (
                                        <p>
                                            Started:{" "}
                                            {new Date(
                                                cycle.startedAt,
                                            ).toLocaleString("en-GB")}
                                        </p>
                                    )}
                                    {cycle.endedAt && (
                                        <p>
                                            Ended:{" "}
                                            {new Date(
                                                cycle.endedAt,
                                            ).toLocaleString("en-GB")}
                                        </p>
                                    )}
                                </div>
                            </details>
                        )}
                    </div>
                </div>
            </td>
            <td className="hidden w-56 align-top sm:table-cell">
                <CycleDates cycle={cycle} />
            </td>
            <td className="w-10 align-top text-right">
                {cycle.editHref && (
                    <ButtonLink
                        href={cycle.editHref}
                        variant="ghost"
                        size="sm"
                        aria-label={`Edit ${cycle.name}`}
                        title={`Edit ${cycle.name}`}
                    >
                        <Icon name="pencil" />
                    </ButtonLink>
                )}
            </td>
        </tr>
    );
}

function phaseRewards(phase: Phase) {
    const rewards: string[] = [];
    for (const outcome of ["win", "draw", "loss"] as const) {
        const reward = phase.rewards[outcome];
        if (!reward) continue;
        const amounts: string[] = [];
        if (reward.credits.fixed || reward.credits.dice)
            amounts.push(creditsText(reward.credits));
        if (reward.reputation) amounts.push(`${reward.reputation} reputation`);
        if (amounts.length)
            rewards.push(
                `${{ win: "Win", draw: "Draw", loss: "Loss" }[outcome]}: ${amounts.join(", ")}`,
            );
    }
    const entry = phase.rewards.entry_credits;
    if (entry?.fixed || entry?.dice)
        rewards.push(`Phase entry: ${creditsText(entry)}`);
    return rewards.join(" · ");
}

function PhaseGroup({
    phase,
    cycles,
    anchor,
    canManage,
}: {
    phase: Phase;
    cycles: Cycle[];
    anchor: boolean;
    canManage: boolean;
}) {
    const heading = `phase-heading-${cycles[0]?.key ?? phase.id}`;
    const projected = cycles.filter(
        (cycle) => cycle.state === "Projected",
    ).length;
    const rewards = phaseRewards(phase);
    return (
        <section
            id={anchor ? `phase-${phase.id}` : undefined}
            aria-labelledby={heading}
        >
            <ActionBar spaced={false} className="rounded-none">
                <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <h3 id={heading} className="font-semibold">
                            {phase.name}
                        </h3>
                        {cycles.some((cycle) => cycle.state === "Current") && (
                            <Badge color="amber">Current phase</Badge>
                        )}
                        <span className="text-xs text-muted">
                            {cycles.length}{" "}
                            {cycles.length === 1 ? "cycle" : "cycles"}
                            {projected ? ` · ${projected} projected` : ""}
                        </span>
                    </div>
                    {phase.description && (
                        <p className="mt-1 whitespace-pre-wrap text-sm text-muted">
                            {phase.description}
                        </p>
                    )}
                    {rewards && <p className="mt-1 text-xs">{rewards}</p>}
                    {phase.effects && (
                        <p className="mt-1 whitespace-pre-wrap text-sm">
                            {phase.effects}
                        </p>
                    )}
                </div>
                {canManage && phase.editHref && (
                    <div className="flex shrink-0 items-center gap-1">
                        <ButtonLink
                            href={phase.editHref}
                            variant="ghost"
                            size="sm"
                            aria-label={`Edit ${phase.name}`}
                            title={`Edit ${phase.name}`}
                        >
                            <Icon name="pencil" />
                        </ButtonLink>
                        <ActionMenu
                            label={`More actions for ${phase.name}`}
                            variant="ghost"
                            align="end"
                            items={[
                                ...(phase.duplicateHref
                                    ? [
                                          {
                                              label: "Duplicate phase",
                                              href: phase.duplicateHref,
                                              tone: "default" as const,
                                              separatorBefore: false,
                                          },
                                      ]
                                    : []),
                                ...(phase.deleteHref
                                    ? [
                                          {
                                              label: "Delete phase",
                                              href: phase.deleteHref,
                                              tone: "danger" as const,
                                              separatorBefore: true,
                                          },
                                      ]
                                    : []),
                            ]}
                        />
                    </div>
                )}
            </ActionBar>
            {cycles.length ? (
                <Table className="[&_td]:py-1.5!">
                    <caption className="sr-only">{phase.name} cycles</caption>
                    <thead className="sr-only">
                        <tr>
                            <th scope="col">Cycle</th>
                            <th scope="col" className="hidden sm:table-cell">
                                Dates
                            </th>
                            <th scope="col">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {cycles.map((cycle) => (
                            <CycleRow key={cycle.key} cycle={cycle} />
                        ))}
                    </tbody>
                </Table>
            ) : (
                <p className="px-3 py-2 text-xs text-muted">
                    No cycles on this page.
                </p>
            )}
        </section>
    );
}

function ScheduleContent(
    props: ScheduleProps & {
        navigation: {
            pending: boolean;
            error: string;
            retry: () => void;
            setGuard: (value: boolean) => void;
        };
    },
) {
    const phases = new Map(props.phases.map((phase) => [phase.id, phase]));
    // A repeated phase starts another group; grouping by identity would reorder cycles.
    const groups: { phase: Phase; cycles: Cycle[]; anchor: boolean }[] = [];
    const shown = new Set<string>();
    for (const cycle of props.rows) {
        const last = groups.at(-1);
        if (last?.phase.id === cycle.phaseId) last.cycles.push(cycle);
        else {
            const phase = phases.get(cycle.phaseId);
            if (phase) {
                groups.push({
                    phase,
                    cycles: [cycle],
                    anchor: !shown.has(phase.id),
                });
                shown.add(phase.id);
            }
        }
    }
    for (const phase of props.phases) {
        if (!shown.has(phase.id))
            groups.push({ phase, cycles: [], anchor: true });
    }
    return (
        <div className="space-y-4">
            <Breadcrumbs
                items={[
                    { label: "Campaigns", href: "/n26/campaigns/" },
                    { label: props.campaignName, href: props.campaignHref },
                    { label: "Cycles" },
                ]}
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-semibold">Campaign cycles</h1>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                        <span className="text-muted">{props.status}</span>
                        {props.configured && (
                            <>
                                <Badge color="amber">{props.currentName}</Badge>
                                <span>{props.currentPhase}</span>
                            </>
                        )}
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    {props.actions.plan && (
                        <ButtonLink href={props.actions.plan} size="sm">
                            Schedule settings
                        </ButtonLink>
                    )}
                    {props.actions.transition && (
                        <ButtonLink
                            href={props.actions.transition}
                            variant="primary"
                            size="sm"
                        >
                            {props.actions.transitionLabel}
                        </ButtonLink>
                    )}
                </div>
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
                <section
                    aria-labelledby="cycle-list-heading"
                    className="space-y-3"
                >
                    {props.dateSettingsRequired && (
                        <p className="text-sm">
                            {props.canManage ? (
                                <>
                                    Set cycle dates in{" "}
                                    <Link href={props.actions.plan}>
                                        Schedule settings
                                    </Link>{" "}
                                    before saving more cycles.
                                </>
                            ) : (
                                "The arbitrator needs to set the saved cycle dates."
                            )}
                        </p>
                    )}
                    <h2 id="cycle-list-heading" className="sr-only">
                        Schedule
                    </h2>
                    {props.plan && (
                        <div className="space-y-1 text-sm">
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                                <strong>
                                    {props.plan.mode === "repeating"
                                        ? "Repeating pattern"
                                        : "Future plan"}
                                </strong>
                                <ol className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                    {props.plan.steps.map((step, index) => (
                                        <li
                                            key={step.id}
                                            className="inline-flex items-center gap-2"
                                        >
                                            {index > 0 && (
                                                <Icon
                                                    name="arrow-right"
                                                    className="size-3 text-muted"
                                                />
                                            )}
                                            <span>
                                                {
                                                    phases.get(step.phase_id)
                                                        ?.name
                                                }{" "}
                                                × {step.count}
                                            </span>
                                        </li>
                                    ))}
                                </ol>
                            </div>
                            <p className="text-xs text-muted">
                                {props.plan.steps.length
                                    ? `Continues after ${props.plan.startsAfter}. `
                                    : "The fixed plan has no remaining projected cycles. "}
                                Projected cycles are previews. Editing one or
                                selecting it for a battle also saves the
                                preceding projected cycles.
                            </p>
                        </div>
                    )}
                    <Card>
                        <div className="-m-4 divide-y divide-box-border overflow-hidden rounded-box">
                            {groups.map((group) => (
                                <PhaseGroup
                                    key={group.cycles[0]?.key ?? group.phase.id}
                                    {...group}
                                    canManage={props.canManage}
                                />
                            ))}
                        </div>
                    </Card>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
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
                        {props.canManage && (
                            <>
                                <Link href={props.actions.template}>
                                    Apply a template
                                </Link>
                                <Link href={props.actions.saveTemplate}>
                                    Save as a template
                                </Link>
                            </>
                        )}
                    </div>
                </section>
            )}
            {props.editor && (
                <ScheduleEditor
                    key={`${props.editor.recoveryKey}:${props.editor.values.request_key}`}
                    editor={props.editor}
                    phases={props.phases}
                    onNavigate={props.onNavigate}
                    onReload={props.onReload}
                    navigation={props.navigation}
                />
            )}
        </div>
    );
}

export function CampaignSchedule(props: ScheduleProps) {
    const navigation = useScheduleNavigation(props);
    return (
        <div onClickCapture={navigation.onClick} aria-busy={navigation.pending}>
            {!navigation.data.editor && navigation.pending && (
                <p role="status" className="mb-3 text-sm text-muted">
                    Loading schedule…
                </p>
            )}
            {!navigation.data.editor && navigation.error && (
                <div role="alert" className="mb-3 text-sm">
                    <p>{navigation.error}</p>
                    <Button size="sm" onClick={navigation.retry}>
                        Try again
                    </Button>
                </div>
            )}
            {navigation.notices.map((notice, index) => (
                <p key={index} role="status" className="mb-3 text-sm">
                    {notice}
                </p>
            ))}
            <ScheduleContent
                {...navigation.data}
                onNavigate={navigation.navigate}
                onReload={navigation.reload}
                navigation={navigation}
            />
        </div>
    );
}
