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
    isPhaseEditor,
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

function CycleRow({ cycle }: { cycle: Cycle }) {
    const projected = cycle.state === "Projected";
    return (
        <tr
            id={`cycle-${cycle.key}`}
            className={
                projected
                    ? "bg-ink-500/[0.025] opacity-60 focus-within:opacity-100 [&_td]:text-muted!"
                    : cycle.state === "Current"
                      ? "bg-accent/5"
                      : ""
            }
        >
            <td className="align-middle [overflow-wrap:anywhere]">
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
                            {projected && (
                                <span className="sr-only">
                                    Preview, not saved yet.
                                    {cycle.editHref &&
                                        " Edit this cycle to save it."}
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
                    {cycle.deleteHref && (
                        <ButtonLink
                            href={cycle.deleteHref}
                            variant="ghost"
                            size="xs"
                            className="inline-flex! size-6! items-center justify-center p-0! leading-none text-danger"
                            aria-label={`Delete ${cycle.name}`}
                            title={`Delete ${cycle.name}`}
                        >
                            <Icon name="trash-2" className="size-3.5" />
                        </ButtonLink>
                    )}
                </div>
            </td>
        </tr>
    );
}

function PhaseGroup({
    phase,
    number,
    cycles,
    anchor,
    canManage,
}: {
    phase: Phase;
    number: number;
    cycles: Cycle[];
    anchor: boolean;
    canManage: boolean;
}) {
    const heading = `phase-heading-${cycles[0]?.key ?? phase.id}`;
    const actions: ActionMenuItem[] = [
        {
            label: "Edit",
            href: phase.editHref,
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
            separatorBefore: !!(phase.editHref || phase.duplicateHref),
        },
    ];
    const availableActions = actions.filter((action) => action.href);
    return (
        <section
            id={anchor ? `phase-${phase.id}` : undefined}
            aria-labelledby={heading}
            className="space-y-2"
        >
            <div className="px-1">
                <PhaseSummary
                    {...phase}
                    number={number}
                    count={cycles.length}
                    headingId={heading}
                    status={
                        cycles.some((cycle) => cycle.state === "Current") ? (
                            <Badge color="amber">Current phase</Badge>
                        ) : undefined
                    }
                    actions={
                        canManage && availableActions.length > 0 ? (
                            <ActionMenu
                                label={`More actions for ${phase.name}`}
                                items={availableActions}
                                variant="ghost"
                                align="end"
                            />
                        ) : undefined
                    }
                />
            </div>
            {cycles.length ? (
                <Card>
                    <div className="-m-4 overflow-hidden rounded-box">
                        <Table hover={false} className="[&_td]:py-2!">
                            <caption className="sr-only">
                                {phase.name} cycles
                            </caption>
                            <thead className="sr-only">
                                <tr>
                                    <th scope="col">Cycle</th>
                                    <th
                                        scope="col"
                                        className="hidden sm:table-cell"
                                    >
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
                    </div>
                </Card>
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
    if (isPageEditor(props.editor))
        return (
            <ScheduleEditor
                key={`${props.editor.recoveryKey}:${props.editor.values.request_key}`}
                editor={props.editor}
                phases={props.phases}
                addPhaseHref={props.actions.addPhase}
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
                            ...(isPhaseEditor(props.editor)
                                ? [
                                      {
                                          label: "Settings",
                                          href: props.editor.back,
                                      },
                                  ]
                                : []),
                            { label: props.editor.heading },
                        ]}
                    />
                }
                onNavigate={props.onNavigate}
                onReload={props.onReload}
                navigation={props.navigation}
            />
        );
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
                    {!props.phases.length && (
                        <p className="text-sm text-muted">
                            No phases in this schedule. Add a phase, then choose
                            its cycles in Settings.
                        </p>
                    )}
                    <div className="space-y-4">
                        {groups.map((group) => (
                            <PhaseGroup
                                key={group.cycles[0]?.key ?? group.phase.id}
                                {...group}
                                number={
                                    group.phase.number ??
                                    props.phases.findIndex(
                                        (phase) => phase.id === group.phase.id,
                                    ) + 1
                                }
                                canManage={props.canManage}
                            />
                        ))}
                    </div>
                    {props.rows.some(
                        (cycle) => cycle.state === "Projected",
                    ) && (
                        <p className="text-xs text-muted">
                            Grey cycles are previews. Previewing does not change
                            your schedule.
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
