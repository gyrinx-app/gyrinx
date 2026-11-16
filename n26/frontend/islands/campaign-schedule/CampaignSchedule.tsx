import {
    ActionMenu,
    type ActionMenuItem,
    Alert,
    Badge,
    BusyControlScope,
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
import { PhaseSummary } from "./PhaseSummary";
import {
    isPageEditor,
    type Cycle,
    type Phase,
    type ScheduleProps,
} from "./types";

export { creditsText } from "./PhaseSummary";

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
    const start = cycle.startsOn
        ? dateText(cycle.startsOn)
        : "Start date not set";
    const end = cycle.endsOn ? dateText(cycle.endsOn) : "End date not set";
    const description =
        cycle.startsOn || cycle.endsOn
            ? `${cycle.startsOn ? `Start date ${start}` : start}, ${cycle.endsOn ? `end date ${end}` : end}`
            : "Dates not set";
    const range =
        cycle.startsOn || cycle.endsOn ? (
            <span className="inline-flex items-center gap-1 whitespace-nowrap">
                {cycle.startsOn ? (
                    <>
                        <span className="sr-only">Start date:</span>
                        <time dateTime={cycle.startsOn}>{start}</time>
                    </>
                ) : (
                    start
                )}
                <span aria-hidden="true">–</span>
                {cycle.endsOn ? (
                    <>
                        <span className="sr-only">End date:</span>
                        <time dateTime={cycle.endsOn}>{end}</time>
                    </>
                ) : (
                    end
                )}
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
            tone={cycle.state === "Projected" ? "current" : "accent"}
            className={`inline-block py-1 text-xs ${cycle.state === "Projected" ? "text-muted!" : ""}`}
            aria-label={`Edit dates for ${cycle.name}: ${description}`}
            title="Edit start and end dates"
        >
            {range}
        </Link>
    );
}

function CycleRow({
    cycle: original,
    canManage,
}: {
    cycle: Cycle;
    canManage: boolean;
}) {
    const projected = original.state === "Projected";
    const cycle =
        canManage && (!projected || original.editablePreview)
            ? original
            : {
                  ...original,
                  editHref: "",
                  deleteHref: "",
                  duplicateHref: "",
                  moveHref: "",
              };
    const actions: ActionMenuItem[] = [
        {
            label: "Move",
            href: cycle.moveHref ?? "",
            tone: "default",
            separatorBefore: false,
        },
        {
            label: "Duplicate",
            href: cycle.duplicateHref ?? "",
            tone: "default",
            separatorBefore: false,
        },
        {
            label: "Delete",
            href: cycle.deleteHref ?? "",
            tone: "danger",
            separatorBefore: !!(cycle.moveHref || cycle.duplicateHref),
        },
    ].filter((item) => item.href) as ActionMenuItem[];
    return (
        <tr
            id={`cycle-${cycle.key}`}
            className={
                projected
                    ? "bg-ink-500/[0.025] [&_td]:text-muted!"
                    : cycle.state === "Current"
                      ? "bg-accent/5"
                      : ""
            }
        >
            <td className="align-middle [overflow-wrap:anywhere]">
                <div className="flex items-start gap-2">
                    <span
                        className="w-5 shrink-0 text-sm font-medium tabular-nums text-muted"
                        aria-hidden="true"
                    >
                        {String(cycle.order).padStart(2, "0")}
                    </span>
                    <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                            <span className="font-medium">{cycle.name}</span>
                            {projected && (
                                <span className="sr-only">
                                    Generated preview, not saved yet.
                                </span>
                            )}
                            {(cycle.state === "Current" ||
                                cycle.state === "Past") && (
                                <Badge
                                    color={
                                        cycle.state === "Current"
                                            ? "amber"
                                            : "ink"
                                    }
                                >
                                    {cycle.state}
                                </Badge>
                            )}
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
            <td className="hidden w-56 align-middle sm:table-cell">
                <CycleDates cycle={cycle} />
            </td>
            <td className="w-16 align-middle text-right">
                <div className="flex justify-end gap-1">
                    {cycle.editHref && (
                        <ButtonLink
                            href={cycle.editHref}
                            variant="ghost"
                            size="xs"
                            className="inline-flex! size-6! items-center justify-center p-0! leading-none"
                            aria-label={`Edit ${cycle.name}`}
                            title={`Edit ${cycle.name}`}
                        >
                            <Icon name="pencil" className="size-3.5" />
                        </ButtonLink>
                    )}
                    {actions.length > 0 && (
                        <ActionMenu
                            label={
                                cycle.occurrenceId
                                    ? `More actions for cycle ${String(cycle.order).padStart(2, "0")}: ${cycle.name}`
                                    : `More actions for ${cycle.name}`
                            }
                            items={actions}
                            variant="ghost"
                            trigger="inline-chevron"
                            align="end"
                        />
                    )}
                </div>
            </td>
        </tr>
    );
}

function CycleTable({
    cycles,
    name,
    canManage,
}: {
    cycles: Cycle[];
    name: string;
    canManage: boolean;
}) {
    return (
        <Card>
            <div className="-m-4 overflow-hidden rounded-box">
                <Table hover={false} className="[&_td]:py-2!">
                    <caption className="sr-only">{name} cycles</caption>
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
                            <CycleRow
                                key={cycle.key}
                                cycle={cycle}
                                canManage={canManage}
                            />
                        ))}
                    </tbody>
                </Table>
            </div>
        </Card>
    );
}

function PhaseGroup({
    phase,
    number,
    cycles,
    anchor,
    canManage,
    firstGenerated,
    patternHref,
    planCyclesHref,
}: {
    phase: Phase;
    number: number;
    cycles: Cycle[];
    anchor: boolean;
    canManage: boolean;
    firstGenerated: boolean;
    patternHref?: string;
    planCyclesHref?: string;
}) {
    const heading = `phase-heading-${phase.id}-${cycles[0]?.key ?? "empty"}`;
    const concrete = cycles.filter((cycle) => cycle.state !== "Projected");
    const projected = cycles.filter((cycle) => cycle.state === "Projected");
    const editable = canManage && !phase.generated;
    const actions: ActionMenuItem[] = [
        {
            label: "Edit",
            href: phase.editHref,
            tone: "default",
            separatorBefore: false,
        },
        {
            label: "Move",
            href: phase.moveHref ?? "",
            tone: "default",
            separatorBefore: false,
        },
        {
            label: "Duplicate",
            href: phase.duplicateHref,
            tone: "default",
            separatorBefore: false,
        },
        {
            label: "Delete",
            href: phase.deleteHref,
            tone: "danger",
            separatorBefore: !!(
                phase.editHref ||
                phase.duplicateHref ||
                phase.moveHref
            ),
        },
    ];
    const available = actions.filter((action) => action.href);
    const continuation = projected.some(
        (cycle) => cycle.editablePreview,
    ) ? null : (
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
            <p>
                Generated repeat continuation. Added cycles move this preview
                later.
            </p>
            {canManage && (planCyclesHref || patternHref) && (
                <div className="flex flex-wrap items-center gap-2">
                    {planCyclesHref && (
                        <ButtonLink
                            href={planCyclesHref}
                            size="sm"
                            variant="ghost"
                        >
                            <Icon name="plus" /> Add from pattern
                        </ButtonLink>
                    )}
                    {patternHref && (
                        <ButtonLink
                            href={patternHref}
                            size="sm"
                            variant="ghost"
                        >
                            Edit repeating pattern
                        </ButtonLink>
                    )}
                </div>
            )}
        </div>
    );
    return (
        <section
            id={anchor ? `phase-${phase.id}` : undefined}
            aria-labelledby={heading}
            className={phase.generated ? "space-y-2 text-muted" : "space-y-2"}
        >
            {phase.generated && firstGenerated && continuation}
            <div className="px-1">
                <PhaseSummary
                    {...phase}
                    number={number}
                    count={
                        phase.generated
                            ? projected.length
                            : Math.max(phase.count, concrete.length) +
                              projected.length
                    }
                    headingId={heading}
                    status={
                        cycles.some((cycle) => cycle.state === "Current") ? (
                            <Badge color="amber">Current phase</Badge>
                        ) : undefined
                    }
                    actions={
                        editable && available.length > 0 ? (
                            <ActionMenu
                                label={
                                    phase.phaseId
                                        ? `More actions for phase ${String(number).padStart(2, "0")}: ${phase.name}`
                                        : `More actions for ${phase.name}`
                                }
                                items={available}
                                variant="ghost"
                                trigger="inline-chevron"
                                align="end"
                            />
                        ) : undefined
                    }
                />
            </div>
            {concrete.length > 0 && (
                <CycleTable
                    cycles={concrete}
                    name={phase.name}
                    canManage={editable}
                />
            )}
            {!concrete.length && !phase.generated && !projected.length && (
                <p className="px-1 py-2 text-sm text-muted">
                    No cycles in this phase.
                </p>
            )}
            {editable && (phase.addCycleHref || phase.addPhaseHref) && (
                <div className="flex flex-wrap gap-2">
                    {phase.addCycleHref && (
                        <ButtonLink
                            href={phase.addCycleHref}
                            size="sm"
                            variant="ghost"
                            aria-label={`Add cycle to phase ${String(number).padStart(2, "0")}: ${phase.name}`}
                        >
                            <Icon name="plus" /> Add cycle
                        </ButtonLink>
                    )}
                    {phase.addPhaseHref && (
                        <ButtonLink
                            href={phase.addPhaseHref}
                            size="sm"
                            variant="ghost"
                            aria-label={`Add phase after ${String(number).padStart(2, "0")}: ${phase.name}`}
                        >
                            <Icon name="plus" /> Add phase
                        </ButtonLink>
                    )}
                </div>
            )}
            {!phase.generated && firstGenerated && continuation}
            {projected.length > 0 && (
                <CycleTable
                    cycles={projected}
                    name={`${phase.name} generated`}
                    canManage={canManage}
                />
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
    if (isPageEditor(props.editor))
        return (
            <ScheduleEditor
                key={`${props.editor.recoveryKey}:${props.editor.values.request_key}`}
                editor={props.editor}
                phases={props.phases}
                breadcrumb={
                    <Breadcrumbs
                        items={[
                            { label: "Campaigns", href: "/n26/campaigns/" },
                            {
                                label: props.campaignName,
                                href: props.campaignHref,
                            },
                            {
                                label: "Phases & cycles",
                                href: props.scheduleHref,
                            },
                            { label: props.editor.heading },
                        ]}
                    />
                }
                onNavigate={props.onNavigate}
                onReload={props.onReload}
                navigation={props.navigation}
            />
        );
    const phases = new Map(
        props.phases.map((phase) => [phase.phaseId ?? phase.id, phase]),
    );
    const groups: { phase: Phase; cycles: Cycle[]; anchor: boolean }[] = [];
    if (
        props.phases.some((phase) => phase.phaseId !== undefined) ||
        props.rows.some((cycle) => cycle.occurrenceId)
    ) {
        for (const phase of props.phases) {
            const cycles = props.rows.filter(
                (cycle) => cycle.occurrenceId === phase.id,
            );
            if (cycles.length || (!phase.generated && phase.count === 0))
                groups.push({ phase, cycles, anchor: true });
        }
    } else {
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
    }
    const firstGenerated = groups.findIndex((group) =>
        group.cycles.some((cycle) => cycle.state === "Projected"),
    );
    return (
        <div className="space-y-4">
            <Breadcrumbs
                items={[
                    { label: "Campaigns", href: "/n26/campaigns/" },
                    { label: props.campaignName, href: props.campaignHref },
                    { label: "Phases & cycles" },
                ]}
            />
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-semibold">Phases & cycles</h1>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-sm">
                        <span className="text-muted">{props.status}</span>
                        {props.configured &&
                            (props.currentPhaseId ? (
                                <>
                                    <Badge color="amber">
                                        {props.currentName}
                                    </Badge>
                                    <span>{props.currentPhase}</span>
                                </>
                            ) : (
                                <span className="text-muted">
                                    No current cycle
                                </span>
                            ))}
                    </div>
                </div>
                <div className="flex flex-wrap gap-2">
                    {props.actions.plan && (
                        <ButtonLink href={props.actions.plan} size="sm">
                            Settings
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
                            Set up phases & cycles
                        </ButtonLink>
                    )}
                </Card>
            ) : (
                <section
                    aria-labelledby="cycle-list-heading"
                    className="space-y-3"
                >
                    <h2 id="cycle-list-heading" className="sr-only">
                        Schedule
                    </h2>
                    {!props.phases.some((phase) => !phase.generated) && (
                        <div className="space-y-2">
                            <p className="text-sm text-muted">
                                {props.canManage
                                    ? "Add a phase to start planning this campaign’s cycles."
                                    : "The arbitrator has not added any phases yet."}
                            </p>
                            {props.canManage && props.actions.addPhase && (
                                <ButtonLink
                                    href={props.actions.addPhase}
                                    variant="primary"
                                    size="sm"
                                >
                                    Add phase
                                </ButtonLink>
                            )}
                        </div>
                    )}
                    <div className="space-y-4">
                        {groups.map((group, index) => (
                            <PhaseGroup
                                key={
                                    group.phase.id +
                                    (group.cycles[0]?.key ?? "empty")
                                }
                                {...group}
                                number={
                                    group.phase.number ??
                                    props.phases.findIndex(
                                        (phase) => phase.id === group.phase.id,
                                    ) + 1
                                }
                                canManage={props.canManage}
                                firstGenerated={index === firstGenerated}
                                patternHref={props.actions.pattern}
                                planCyclesHref={props.actions.planCycles}
                            />
                        ))}
                    </div>
                    {props.canManage &&
                        firstGenerated < 0 &&
                        (props.actions.planCycles || props.actions.pattern) && (
                            <div className="flex flex-wrap gap-2">
                                {props.actions.planCycles && (
                                    <ButtonLink
                                        href={props.actions.planCycles}
                                        size="sm"
                                        variant="ghost"
                                    >
                                        <Icon name="plus" /> Add from pattern
                                    </ButtonLink>
                                )}
                                {props.actions.pattern && (
                                    <ButtonLink
                                        href={props.actions.pattern}
                                        size="sm"
                                        variant="ghost"
                                    >
                                        Edit repeating pattern
                                    </ButtonLink>
                                )}
                            </div>
                        )}
                    {props.rows.some(
                        (cycle) => cycle.state === "Projected",
                    ) && (
                        <p className="text-xs text-muted">
                            Grey cycles are generated previews. Previewing does
                            not change your schedule.
                        </p>
                    )}
                    {props.plan && !props.nextHref && (
                        <div className="space-y-2 border-t border-dashed border-box-border pt-3 text-sm text-muted">
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                                <strong>
                                    {props.plan.mode === "repeating"
                                        ? "Repeating pattern"
                                        : "Remaining cycles"}
                                </strong>
                                <ol className="flex flex-wrap items-center gap-x-2 gap-y-1">
                                    {props.plan.steps.map((step, index) => (
                                        <li
                                            key={`${step.id}-${index}`}
                                            className="inline-flex items-center gap-2"
                                        >
                                            {index > 0 && (
                                                <Icon
                                                    name="arrow-right"
                                                    className="size-3 text-muted"
                                                />
                                            )}
                                            <span>
                                                {props.plan?.phaseNames?.[
                                                    step.phase_id
                                                ] ??
                                                    phases.get(step.phase_id)
                                                        ?.name}{" "}
                                                × {step.count}
                                            </span>
                                        </li>
                                    ))}
                                </ol>
                            </div>
                            <p className="text-xs">
                                {props.plan.mode === "repeating"
                                    ? "This pattern repeats until the campaign finishes."
                                    : `Continues after ${props.plan.startsAfter}.`}
                            </p>
                        </div>
                    )}
                    {(props.previousHref ||
                        props.nextHref ||
                        props.moreHref) && (
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                            {props.previousHref && (
                                <Link href={props.previousHref}>
                                    Earlier cycles
                                </Link>
                            )}
                            {props.nextHref && (
                                <Link href={props.nextHref}>Later cycles</Link>
                            )}
                            {props.moreHref && (
                                <Link href={props.moreHref}>
                                    Preview more cycles
                                </Link>
                            )}
                        </div>
                    )}
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
        <BusyControlScope value={navigation.busyControl}>
            <div
                data-busy="off"
                onClickCapture={navigation.onClick}
                aria-busy={navigation.pending}
            >
                {!navigation.data.editor && navigation.error && (
                    <Alert tone="error" dismissible={false} className="mb-3">
                        <p>{navigation.error}</p>
                        <Button size="sm" onClick={navigation.retry}>
                            Try again
                        </Button>
                    </Alert>
                )}
                {navigation.notices.map((notice) => (
                    <Alert key={notice.id} tone={notice.tone} className="mb-3">
                        {notice.message}
                    </Alert>
                ))}
                <ScheduleContent
                    {...navigation.data}
                    onNavigate={navigation.navigate}
                    onReload={navigation.reload}
                    navigation={navigation}
                />
            </div>
        </BusyControlScope>
    );
}
