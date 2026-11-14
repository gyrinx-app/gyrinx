import React from "react";
import {
    Check,
    ChevronUp,
    ChevronDown,
    Copy,
    GripVertical,
    Pencil,
    Plus,
    Settings2,
    Trash2,
} from "lucide-react";
import { Button, Icon } from "./controls.jsx";
import { CampaignCard } from "./campaign-view.jsx";
import { IconAction, Tag, fmt } from "./campaign-ui.jsx";
import { useCampaignDrag } from "./campaign-drag.js";
import * as M from "./campaign-model.js";

function MoveActions({ label, index, count, move }) {
    return (
        <>
            <IconAction
                icon={ChevronUp}
                label={`Move ${label} earlier`}
                disabled={index === 0}
                onClick={() => move(-1)}
            />
            <IconAction
                icon={ChevronDown}
                label={`Move ${label} later`}
                disabled={index === count - 1}
                onClick={() => move(1)}
            />
        </>
    );
}

function PhaseHeader({ phase, index, state, arbitrator, change, openModal }) {
    const count = state.cycles.filter((c) => c.phase === phase.id).length,
        completed = M.phaseCompleted(state, phase.id);
    return (
        <div
            className={`cp-phase-item ${phase.id === state.currentPhase ? "cp-phase-active" : ""}`}
        >
            <div className="cp-phase-summary">
                <div className="cp-inline">
                    <span className="cp-phase-index">
                        {String(index + 1).padStart(2, "0")}
                    </span>
                    <h3>{phase.name}</h3>
                    {phase.id === state.currentPhase && !state.ended && (
                        <Tag active>Current</Tag>
                    )}
                    {completed && (
                        <>
                            <Tag>Completed</Tag>
                            <span className="cp-help">
                                {M.phaseEndedDate(state, phase.id)}
                            </span>
                        </>
                    )}
                    <span className="cp-help">
                        {count} {count === 1 ? "cycle" : "cycles"}
                    </span>
                </div>
                <p title={phase.description}>
                    {phase.description || "No description."}
                </p>
                <div className="cp-phase-meta">
                    <span>{phase.rewards.win.credits}¢ for a win</span>
                    {phase.grant > 0 && (
                        <span>{fmt(phase.grant)}¢ on entry</span>
                    )}
                </div>
            </div>
            {arbitrator && (
                <div className="cp-phase-tools">
                    <IconAction
                        icon={Copy}
                        label={`Duplicate ${phase.name}`}
                        onClick={() =>
                            change(
                                (s) => M.duplicatePhase(s, phase.id),
                                "Phase duplicated.",
                            )
                        }
                    />
                    <MoveActions
                        label={phase.name}
                        index={index}
                        count={state.phases.length}
                        move={(direction) =>
                            change(
                                (s) => M.reorderPhase(s, phase.id, direction),
                                "Phase order updated.",
                            )
                        }
                    />
                    <IconAction
                        icon={Pencil}
                        label={`Edit ${phase.name}`}
                        onClick={() =>
                            openModal({ kind: "phase", value: phase })
                        }
                    />
                    {M.canRemovePhase(state, phase.id) && (
                        <IconAction
                            icon={Trash2}
                            label={`Remove ${phase.name}`}
                            onClick={() =>
                                change(
                                    (s) => M.removePhase(s, phase.id),
                                    "Phase removed.",
                                )
                            }
                        />
                    )}
                </div>
            )}
        </div>
    );
}

function CycleActions({ cycle, state, phaseIndex, change, openModal }) {
    const current = cycle.id === state.currentCycle,
        completed = state.closedCycles.includes(cycle.id),
        deleteReason = M.cycleDeleteReason(state, cycle.id);
    function moveAdjacent(direction) {
        change((s) => {
            const from = s.cycles.findIndex((c) => c.id === cycle.id),
                target = s.cycles[from + direction];
            const beforeId =
                direction < 0
                    ? target.id
                    : s.cycles[from + 2]?.phase === target.phase
                      ? s.cycles[from + 2].id
                      : null;
            M.moveCycle(s, cycle.id, target.phase, beforeId);
        }, "Cycle moved.");
    }
    return (
        <>
            {current && !completed ? (
                <>
                    <IconAction
                        icon={ChevronUp}
                        label={`Move ${cycle.name} to previous phase`}
                        disabled={phaseIndex === 0}
                        onClick={() =>
                            change(
                                (s) =>
                                    M.moveCycle(
                                        s,
                                        cycle.id,
                                        s.phases[phaseIndex - 1].id,
                                    ),
                                "Current cycle moved.",
                            )
                        }
                    />
                    <IconAction
                        icon={ChevronDown}
                        label={`Move ${cycle.name} to next phase`}
                        disabled={phaseIndex === state.phases.length - 1}
                        onClick={() =>
                            change(
                                (s) =>
                                    M.moveCycle(
                                        s,
                                        cycle.id,
                                        s.phases[phaseIndex + 1].id,
                                    ),
                                "Current cycle moved.",
                            )
                        }
                    />
                </>
            ) : (
                !completed && (
                    <>
                        <IconAction
                            icon={ChevronUp}
                            label={`Move ${cycle.name} earlier`}
                            disabled={
                                cycle.number <= M.currentCycle(state).number + 1
                            }
                            onClick={() => moveAdjacent(-1)}
                        />
                        <IconAction
                            icon={ChevronDown}
                            label={`Move ${cycle.name} later`}
                            disabled={cycle.number === state.cycles.length}
                            onClick={() => moveAdjacent(1)}
                        />
                    </>
                )
            )}
            <IconAction
                icon={Trash2}
                label={`Delete ${cycle.name}`}
                reason={deleteReason}
                onClick={() =>
                    openModal({ kind: "delete-cycle", value: cycle })
                }
            />
            <IconAction
                icon={Pencil}
                label={`Edit ${cycle.name}`}
                onClick={() => openModal({ kind: "cycle", value: cycle })}
            />
        </>
    );
}

function CycleRow({
    cycle,
    state,
    phaseIndex,
    arbitrator,
    change,
    openModal,
    drag,
}) {
    const current = cycle.id === state.currentCycle,
        completed = state.closedCycles.includes(cycle.id),
        dates = M.dates(state, cycle),
        movable = arbitrator && !state.ended && !completed;
    return (
        <div
            className={`cp-cycle-item ${current ? "cp-cycle-current" : ""} ${drag.dragging === cycle.id ? "cp-drag-source" : ""}`}
            data-cycle-id={cycle.id}
            {...drag.cycleProps(cycle)}
        >
            <span
                className="cp-drag-handle"
                title={
                    movable ? "Drag to move cycle" : "Cycle stays as recorded"
                }
            >
                <Icon icon={movable ? GripVertical : Check} size={16} />
            </span>
            <span className={`cp-cycle-dot ${completed ? "cp-done" : ""}`}>
                {cycle.number}
            </span>
            <div className="cp-cycle-copy">
                <div className="cp-inline">
                    <h3>{cycle.name}</h3>
                    {current && (
                        <Tag active>
                            {state.ended ? "Final cycle" : "Current"}
                        </Tag>
                    )}
                    {completed && (
                        <>
                            <Tag>Completed</Tag>
                            <span className="cp-help cp-ended-date">
                                {M.endedDate(cycle.endedAt)}
                            </span>
                        </>
                    )}
                </div>
                {dates && <p>{dates}</p>}
                {cycle.description && (
                    <p title={cycle.description}>{cycle.description}</p>
                )}
            </div>
            <div className="cp-cycle-end">
                <span className="cp-help">
                    {state.battles.filter((b) => b.cycle === cycle.id).length}{" "}
                    battles
                </span>
                {arbitrator && (
                    <CycleActions
                        {...{ cycle, state, phaseIndex, change, openModal }}
                    />
                )}
            </div>
        </div>
    );
}

function DropPreview({ phase, beforeId, state, drag }) {
    const { hover, dragging } = drag;
    if (
        !dragging ||
        !hover?.valid ||
        hover.phase !== phase.id ||
        hover.before !== beforeId
    )
        return null;
    const cycle = state.cycles.find((c) => c.id === dragging);
    if (cycle.phase === phase.id) return null;
    return (
        <div
            className="cp-drag-preview"
            role="status"
            aria-label={`Drop ${cycle.name} in ${phase.name}`}
        >
            <Icon icon={GripVertical} size={14} />
            <strong>{cycle.name}</strong>
            <span className="cp-help">Move here · cycle {hover.index + 1}</span>
        </div>
    );
}

function PatternPosition({ state }) {
    const phases = state.pattern.steps.flatMap((step) =>
        Array(step.cycles).fill(step.phase),
    );
    const current =
        state.pattern.currentIndex === undefined
            ? ((state.pattern.cursor || 0) + phases.length - 1) % phases.length
            : state.pattern.currentIndex;
    return (
        <div
            className="cp-pattern-position text-sm"
            aria-label="Current position in repeating pattern"
        >
            {phases.map((phase, index) => (
                <React.Fragment key={index}>
                    {index > 0 && <span aria-hidden="true"> → </span>}
                    {index === current ? (
                        <strong aria-current="step">
                            {M.getPhase(state, phase).name}
                        </strong>
                    ) : (
                        <span>{M.getPhase(state, phase).name}</span>
                    )}
                </React.Fragment>
            ))}{" "}
            <span aria-hidden="true"> ↻</span>
        </div>
    );
}
export function CampaignSchedule({ state, arbitrator, change, openModal }) {
    const drag = useCampaignDrag(state, change, arbitrator),
        duration =
            state.limit === null
                ? "Unlimited cycles"
                : `${state.cycles.length} total cycles`;
    return (
        <>
            <CampaignCard
                title=""
                headingControl={
                    arbitrator ? (
                        <span className="text-lg font-semibold">
                            {state.limit === null
                                ? "Unlimited campaign"
                                : "Fixed campaign"}
                        </span>
                    ) : (
                        <span className="cp-inline">
                            <span className="text-lg font-semibold">
                                Schedule
                            </span>
                            <span className="text-xs text-muted">
                                {duration}
                            </span>
                        </span>
                    )
                }
                action={
                    arbitrator && (
                        <span className="cp-inline">
                            <Button
                                variant="default"
                                icon={Settings2}
                                onClick={() => openModal({ kind: "settings" })}
                            >
                                Schedule settings
                            </Button>
                            {!state.ended && (
                                <Button
                                    variant="primary"
                                    onClick={() =>
                                        openModal({ kind: "end-cycle" })
                                    }
                                >
                                    {M.endCycleLabel(state)}
                                </Button>
                            )}
                        </span>
                    )
                }
            >
                {M.automaticChangeLabel(state) && (
                    <p className="cp-card-note cp-auto-cycle-next">
                        {M.automaticChangeLabel(state)}
                    </p>
                )}
                {arbitrator && (
                    <p className="cp-card-note">
                        {arbitrator &&
                            (state.limit === null
                                ? "Unlimited cycles. Only current and past cycles are shown."
                                : `${duration}.`)}
                        {arbitrator && (
                            <>
                                {state.limit !== null &&
                                    " Drag upcoming cycles to reorder them or move them into another phase."}{" "}
                                Moving the active cycle changes the campaign
                                phase. Past cycles stay as recorded.
                            </>
                        )}
                    </p>
                )}
                {state.limit === null && state.pattern && (
                    <PatternPosition state={state} />
                )}
                {state.phases.map((phase, index) => (
                    <section
                        key={phase.id}
                        aria-label={`${phase.name} phase`}
                        {...drag.phaseProps(phase.id)}
                    >
                        <PhaseHeader
                            {...{
                                phase,
                                index,
                                state,
                                arbitrator,
                                change,
                                openModal,
                            }}
                        />
                        <div className="cp-phase-cycles">
                            {state.cycles
                                .filter((c) => c.phase === phase.id)
                                .map((cycle) => (
                                    <React.Fragment key={cycle.id}>
                                        <DropPreview
                                            {...{ phase, state, drag }}
                                            beforeId={cycle.id}
                                        />
                                        <CycleRow
                                            {...{
                                                cycle,
                                                state,
                                                arbitrator,
                                                change,
                                                openModal,
                                                drag,
                                            }}
                                            phaseIndex={index}
                                        />
                                    </React.Fragment>
                                ))}
                            <DropPreview
                                {...{ phase, state, drag }}
                                beforeId={null}
                            />
                            {arbitrator && state.limit !== null && (
                                <div className="cp-add-cycle">
                                    <Button
                                        icon={Plus}
                                        aria-label={`Add cycle to ${phase.name}`}
                                        disabled={state.ended}
                                        onClick={() =>
                                            change(
                                                (s) =>
                                                    M.insertCycle(s, phase.id),
                                                "Cycle added.",
                                            )
                                        }
                                    >
                                        Add cycle
                                    </Button>
                                </div>
                            )}
                        </div>
                    </section>
                ))}
            </CampaignCard>
        </>
    );
}
