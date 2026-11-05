import React, { useState } from "react";
import { ArrowRight, ChevronUp, ChevronDown, Plus, Trash2 } from "lucide-react";
import { Button, Icon, TextInput } from "./controls.jsx";
import { Input, Select } from "./surface-controls.jsx";
import * as M from "./campaign-model.js";
import {
    Modal,
    TextArea,
    CheckField,
    FormFoot,
    RewardTable,
    copy,
    gangName,
    cycleOptions,
    phaseOptions,
} from "./campaign-ui.jsx";
import { useUnsavedChanges } from "./campaign-state.js";
export function PhaseForm({ phase, save, close }) {
    const [draft, setDraft] = useState(() => copy(phase));
    const update = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
    return (
        <Modal title="Edit phase" onClose={close}>
            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    save(draft);
                }}
            >
                <Input
                    label="Phase name"
                    value={draft.name}
                    onChange={(v) => update("name", v)}
                    required
                    maxLength={100}
                />
                <TextArea
                    label="Description"
                    value={draft.description}
                    onChange={(v) => update("description", v)}
                    help="Shown beneath the current phase on the campaign dashboard."
                    rows={2}
                />
                <TextArea
                    label="Active effects"
                    value={draft.effects}
                    onChange={(v) => update("effects", v)}
                    help="Describe battle restrictions, table effects or other rules for this phase."
                    rows={3}
                />
                <div className="cp-form-section">
                    <h3>Battle rewards</h3>
                    <p className="cp-help">
                        A fixed amount or a dice expression: 50, d3×10 or
                        2d6×10. Side job rewards are added to the battle
                        outcome.
                    </p>
                    <RewardTable
                        phase={draft}
                        editable
                        onChange={(key, reward) =>
                            update("rewards", {
                                ...draft.rewards,
                                [key]: reward,
                            })
                        }
                    />
                </div>
                <div className="cp-form-section">
                    <h3>When this phase begins</h3>
                    <div className="cp-fields">
                        <Input
                            label="Credits per gang"
                            value={draft.grant}
                            onChange={(v) => update("grant", v)}
                            type="number"
                            min="0"
                            max="1000000"
                            required
                        />
                    </div>
                    <p className="cp-help">
                        Added to each gang’s stash each time the campaign enters
                        this phase. Consecutive cycles in the same phase do not
                        repeat the reward.
                    </p>
                </div>
                <FormFoot onClose={close} />
            </form>
        </Modal>
    );
}
export function CycleForm({ cycle, state, save, close }) {
    const [draft, setDraft] = useState(() => copy(cycle));
    const update = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
    return (
        <Modal title="Edit cycle" onClose={close}>
            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    save({ ...draft, name: draft.name.trim() });
                }}
            >
                <Input
                    label="Cycle name"
                    value={draft.name}
                    onChange={(v) => update("name", v)}
                    required
                    pattern=".*\S.*"
                    maxLength={100}
                />
                <Select
                    label="Phase"
                    value={draft.phase}
                    onChange={(v) => update("phase", v)}
                    options={phaseOptions(state)}
                    disabled={state.closedCycles.includes(draft.id)}
                />
                <p className="cp-help">
                    Changing the current cycle’s phase also changes the campaign
                    phase.
                </p>
                <TextArea
                    label="Description"
                    value={draft.description}
                    onChange={(v) => update("description", v)}
                    rows={3}
                    help="Shown alongside the current cycle on the campaign dashboard."
                />
                <TextArea
                    label="Active effects"
                    value={draft.effects}
                    onChange={(v) => update("effects", v)}
                    rows={2}
                    help="Note any additional effects that apply during this cycle."
                />
                <FormFoot onClose={close} />
            </form>
        </Modal>
    );
}
export function SettingsForm({ state, save, close, closeGuard }) {
    const [draft, setDraft] = useState({
        limit: state.limit,
        start: state.start || "",
        days: state.days || 7,
        repeat: !!state.pattern?.steps?.length,
        autoChange: !!state.autoCycles,
        autoCycles: copy(
            state.autoCycles
                ? M.autoConfig(state.autoCycles)
                : M.defaultAutoCycles(),
        ),
        steps: copy(
            state.pattern?.steps || [
                { phase: state.phases[0].id, cycles: 2 },
                { phase: state.phases[1]?.id || state.phases[0].id, cycles: 1 },
                { phase: state.phases[2]?.id || state.phases[0].id, cycles: 2 },
                { phase: state.phases[1]?.id || state.phases[0].id, cycles: 1 },
            ],
        ),
    });
    const [initialPattern] = useState(() =>
        JSON.stringify({
            repeat: draft.repeat,
            steps: draft.steps,
            unlimited: draft.limit === null,
            autoChange: draft.autoChange,
            autoCycles: draft.autoCycles,
        }),
    );
    const patternDirty =
        (draft.repeat || !!state.pattern) &&
        JSON.stringify({
            repeat: draft.repeat,
            steps: draft.steps,
            unlimited: draft.limit === null,
            autoChange: draft.autoChange,
            autoCycles: draft.autoCycles,
        }) !== initialPattern;
    const scheduledCount = state.cycles
        .slice(state.cycles.findIndex((c) => c.id === state.currentCycle) + 1)
        .filter(
            (c) =>
                !state.closedCycles.includes(c.id) &&
                !state.battles.some((b) => b.cycle === c.id),
        ).length;
    useUnsavedChanges(closeGuard, patternDirty);
    const update = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
    return (
        <Modal title="Schedule settings" onClose={close}>
            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    save(draft);
                }}
            >
                <Select
                    label="Campaign length"
                    value={draft.limit === null ? "unlimited" : "fixed"}
                    options={[
                        ["fixed", "Fixed"],
                        ["unlimited", "Unlimited"],
                    ]}
                    onChange={(v) => {
                        if (
                            v === "unlimited" &&
                            scheduledCount &&
                            !window.confirm(
                                `Switch to no cycle limit? Saving will clear ${scheduledCount} scheduled cycles. Current and past cycles will be kept.`,
                            )
                        )
                            return;
                        update(
                            "limit",
                            v === "unlimited" ? null : state.cycles.length,
                        );
                    }}
                />
                {draft.limit === null && (
                    <div className="cp-form-section cp-pattern-editor">
                        <h3>Repeating phase pattern</h3>
                        <CheckField
                            label="Use a repeating pattern"
                            checked={draft.repeat}
                            onChange={(v) => update("repeat", v)}
                        />
                        {draft.repeat && (
                            <>
                                <p className="cp-help">
                                    Starts next cycle and repeats. Editing
                                    restarts the pattern; moving the active
                                    cycle keeps its place.
                                </p>
                                <div
                                    className="cp-pattern-heading"
                                    aria-hidden="true"
                                >
                                    <span />
                                    <span>Cycles</span>
                                    <span>Phase</span>
                                </div>
                                <ol className="cp-pattern-steps">
                                    {draft.steps.map((step, i) => (
                                        <li key={i} className="cp-pattern-step">
                                            <span className="cp-help">
                                                {i + 1}
                                            </span>
                                            <Input
                                                label={`Cycles in step ${i + 1}`}
                                                type="number"
                                                min="1"
                                                max="100"
                                                required
                                                value={step.cycles}
                                                onChange={(v) =>
                                                    update(
                                                        "steps",
                                                        draft.steps.map(
                                                            (x, j) =>
                                                                j === i
                                                                    ? {
                                                                          ...x,
                                                                          cycles: Number(
                                                                              v,
                                                                          ),
                                                                      }
                                                                    : x,
                                                        ),
                                                    )
                                                }
                                            />
                                            <Select
                                                label={`Phase in step ${i + 1}`}
                                                value={step.phase}
                                                options={phaseOptions(state)}
                                                onChange={(v) =>
                                                    update(
                                                        "steps",
                                                        draft.steps.map(
                                                            (x, j) =>
                                                                j === i
                                                                    ? {
                                                                          ...x,
                                                                          phase: v,
                                                                      }
                                                                    : x,
                                                        ),
                                                    )
                                                }
                                            />
                                            <Button
                                                icon={ChevronUp}
                                                aria-label={`Move pattern step ${i + 1} earlier`}
                                                disabled={i === 0}
                                                onClick={() => {
                                                    const steps = copy(
                                                        draft.steps,
                                                    );
                                                    [steps[i - 1], steps[i]] = [
                                                        steps[i],
                                                        steps[i - 1],
                                                    ];
                                                    update("steps", steps);
                                                }}
                                            />
                                            <Button
                                                icon={ChevronDown}
                                                aria-label={`Move pattern step ${i + 1} later`}
                                                disabled={
                                                    i === draft.steps.length - 1
                                                }
                                                onClick={() => {
                                                    const steps = copy(
                                                        draft.steps,
                                                    );
                                                    [steps[i + 1], steps[i]] = [
                                                        steps[i],
                                                        steps[i + 1],
                                                    ];
                                                    update("steps", steps);
                                                }}
                                            />
                                            <Button
                                                icon={Trash2}
                                                aria-label={`Remove pattern step ${i + 1}`}
                                                disabled={
                                                    draft.steps.length === 1
                                                }
                                                onClick={() =>
                                                    update(
                                                        "steps",
                                                        draft.steps.filter(
                                                            (_, j) => j !== i,
                                                        ),
                                                    )
                                                }
                                            />
                                        </li>
                                    ))}
                                </ol>
                                <Button
                                    icon={Plus}
                                    onClick={() =>
                                        update("steps", [
                                            ...draft.steps,
                                            {
                                                phase: state.phases[0].id,
                                                cycles: 1,
                                            },
                                        ])
                                    }
                                >
                                    Add pattern step
                                </Button>
                                <div className="cp-auto-cycle-settings">
                                    <CheckField
                                        label="Auto-change cycles"
                                        checked={draft.autoChange}
                                        onChange={(v) =>
                                            update("autoChange", v)
                                        }
                                    />
                                    {draft.autoChange && (
                                        <>
                                            <div className="cp-fields">
                                                <Select
                                                    label="Change cycles"
                                                    value={
                                                        draft.autoCycles
                                                            .frequency
                                                    }
                                                    onChange={(frequency) =>
                                                        update("autoCycles", {
                                                            ...draft.autoCycles,
                                                            frequency,
                                                        })
                                                    }
                                                    options={[
                                                        ["weekly", "Weeks"],
                                                        ["monthly", "Monthly"],
                                                    ]}
                                                />
                                                {draft.autoCycles.frequency ===
                                                    "weekly" && (
                                                    <label className="history-field">
                                                        <span className="text-sm font-semibold">
                                                            Interval
                                                        </span>
                                                        <span className="cp-week-interval">
                                                            Every
                                                            <TextInput
                                                                aria-label="Weeks between cycle changes"
                                                                type="number"
                                                                min="1"
                                                                max="520"
                                                                step="1"
                                                                required
                                                                value={
                                                                    draft
                                                                        .autoCycles
                                                                        .weeks
                                                                }
                                                                onChange={(v) =>
                                                                    update(
                                                                        "autoCycles",
                                                                        {
                                                                            ...draft.autoCycles,
                                                                            weeks: Number(
                                                                                v,
                                                                            ),
                                                                        },
                                                                    )
                                                                }
                                                            />
                                                            {draft.autoCycles
                                                                .weeks === 1
                                                                ? "week"
                                                                : "weeks"}
                                                        </span>
                                                    </label>
                                                )}
                                                {draft.autoCycles.frequency ===
                                                "monthly" ? (
                                                    <Input
                                                        label="Day of month"
                                                        type="number"
                                                        min="1"
                                                        max="31"
                                                        required
                                                        value={
                                                            draft.autoCycles
                                                                .monthDay
                                                        }
                                                        onChange={(v) =>
                                                            update(
                                                                "autoCycles",
                                                                {
                                                                    ...draft.autoCycles,
                                                                    monthDay:
                                                                        Number(
                                                                            v,
                                                                        ),
                                                                },
                                                            )
                                                        }
                                                    />
                                                ) : (
                                                    <Select
                                                        label="Day of week"
                                                        value={String(
                                                            draft.autoCycles
                                                                .weekday,
                                                        )}
                                                        onChange={(v) =>
                                                            update(
                                                                "autoCycles",
                                                                {
                                                                    ...draft.autoCycles,
                                                                    weekday:
                                                                        Number(
                                                                            v,
                                                                        ),
                                                                },
                                                            )
                                                        }
                                                        options={[
                                                            "Sunday",
                                                            "Monday",
                                                            "Tuesday",
                                                            "Wednesday",
                                                            "Thursday",
                                                            "Friday",
                                                            "Saturday",
                                                        ].map((label, i) => [
                                                            String(i),
                                                            label,
                                                        ])}
                                                    />
                                                )}
                                                <Input
                                                    label="Change at"
                                                    type="time"
                                                    required
                                                    value={
                                                        draft.autoCycles.time
                                                    }
                                                    onChange={(time) =>
                                                        update("autoCycles", {
                                                            ...draft.autoCycles,
                                                            time,
                                                        })
                                                    }
                                                />
                                                <Input
                                                    label="Time zone"
                                                    required
                                                    value={
                                                        draft.autoCycles
                                                            .timeZone
                                                    }
                                                    onChange={(timeZone) =>
                                                        update("autoCycles", {
                                                            ...draft.autoCycles,
                                                            timeZone,
                                                        })
                                                    }
                                                />
                                            </div>
                                            <p className="cp-help">
                                                Weekly intervals start on the
                                                next selected weekday. Monthly
                                                changes use the last day when a
                                                month is shorter. The demo
                                                catches up missed changes when
                                                reopened.
                                            </p>
                                        </>
                                    )}
                                </div>
                            </>
                        )}
                    </div>
                )}
                {draft.limit !== null && (
                    <>
                        <div className="cp-form-section">
                            <h3>Real-world dates</h3>
                            <CheckField
                                label="Show rough dates for cycles"
                                checked={!!draft.start}
                                onChange={(v) =>
                                    update(
                                        "start",
                                        v
                                            ? new Date()
                                                  .toISOString()
                                                  .slice(0, 10)
                                            : "",
                                    )
                                }
                            />
                            {draft.start && (
                                <div className="cp-fields">
                                    <Input
                                        label="Campaign start date"
                                        value={draft.start}
                                        onChange={(v) => update("start", v)}
                                        type="date"
                                        required
                                    />
                                    <Input
                                        label="Days per cycle"
                                        value={draft.days}
                                        onChange={(v) =>
                                            update("days", Number(v))
                                        }
                                        type="number"
                                        min="1"
                                        max="365"
                                        required
                                    />
                                </div>
                            )}
                            <p className="cp-help">
                                Indicative cycle dates for planning. Cycles
                                still end when the arbitrator chooses.
                            </p>
                        </div>
                    </>
                )}
                {state.limit !== null &&
                    draft.limit === null &&
                    scheduledCount > 0 && (
                        <p className="cp-inline-note" role="status">
                            Saving will clear {scheduledCount} scheduled cycles.
                            Current and past cycles will be kept.
                        </p>
                    )}
                <FormFoot onClose={close} />
            </form>
        </Modal>
    );
}
export function BattleForm({ state, save, close }) {
    const [draft, setDraft] = useState({
        name: "",
        cycle: state.currentCycle,
        phase: state.currentPhase,
        participants: [state.gangs[0].id, state.gangs[1].id],
        winner: state.gangs[0].id,
        sideJobs: [],
    });
    const update = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
    const phase = state.phases.find((p) => p.id === draft.phase);
    return (
        <Modal title="Record a battle" onClose={close}>
            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    save(draft);
                }}
            >
                <Input
                    label="Battle name"
                    value={draft.name}
                    onChange={(v) => update("name", v)}
                    required
                    pattern=".*\S.*"
                    maxLength={120}
                />
                <div className="cp-fields">
                    <Select
                        label="Cycle"
                        value={draft.cycle}
                        onChange={(v) => {
                            const cycle = state.cycles.find((c) => c.id === v);
                            setDraft((d) => ({
                                ...d,
                                cycle: v,
                                phase:
                                    cycle.id === state.currentCycle
                                        ? state.currentPhase
                                        : cycle.phaseHistory?.at(-1) ||
                                          cycle.phase,
                            }));
                        }}
                        options={cycleOptions(state)}
                    />
                    <Select
                        label="Phase at battle"
                        value={draft.phase}
                        onChange={(v) => update("phase", v)}
                        options={phaseOptions(state)}
                    />
                </div>
                <p className="cp-help">
                    These are kept with the battle, including when the phase
                    changes during a cycle.
                </p>
                <div className="cp-fields">
                    {[0, 1].map((i) => (
                        <Select
                            key={i}
                            label={`Gang ${i + 1}`}
                            value={draft.participants[i]}
                            onChange={(v) => {
                                const participants = [...draft.participants];
                                participants[i] = v;
                                setDraft((d) => ({
                                    ...d,
                                    participants,
                                    winner: "draw",
                                    sideJobs: [],
                                }));
                            }}
                            options={state.gangs.map((g) => [g.id, g.name])}
                        />
                    ))}
                </div>
                <Select
                    label="Battle result"
                    value={draft.winner}
                    onChange={(v) => update("winner", v)}
                    options={[
                        ["draw", "Draw"],
                        ...[...new Set(draft.participants)].map((g) => [
                            g,
                            `${gangName(state, g)} won`,
                        ]),
                    ]}
                />
                <fieldset className="cp-form-section">
                    <legend>Side jobs completed</legend>
                    {[...new Set(draft.participants)].map((g) => (
                        <CheckField
                            key={g}
                            label={gangName(state, g)}
                            checked={draft.sideJobs.includes(g)}
                            onChange={(v) =>
                                update(
                                    "sideJobs",
                                    v
                                        ? [...draft.sideJobs, g]
                                        : draft.sideJobs.filter((x) => x !== g),
                                )
                            }
                        />
                    ))}
                </fieldset>
                <details>
                    <summary>Rewards for {phase.name}</summary>
                    <RewardTable phase={phase} />
                </details>
                <p className="cp-inline-note">
                    Recording rolls the configured rewards and adds the credits
                    and reputation to these demo gangs.
                </p>
                <FormFoot onClose={close} label="Record battle" />
            </form>
        </Modal>
    );
}

export function EndCycleForm({ state, save, close }) {
    const current = M.currentCycle(state),
        next = M.nextCycle(state);
    const manual = state.limit === null && !M.nextPatternPhase(state);
    const [currentCycle] = useState(current.id);
    const [name, setName] = useState(`Cycle ${current.number + 1}`),
        [phase, setPhase] = useState(next?.phase || state.currentPhase),
        [skipAutomatic, setSkipAutomatic] = useState(false);
    const nextPhase =
        state.limit === null
            ? M.getPhase(state, phase)
            : next && M.getPhase(state, next.phase);
    return (
        <Modal
            title={
                manual
                    ? "End cycle"
                    : next || state.limit === null
                      ? "End this cycle"
                      : "End the campaign"
            }
            onClose={close}
        >
            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    save({ name, phase, skipAutomatic, currentCycle });
                }}
            >
                {state.limit === null && (
                    <>
                        <Input
                            label="Next cycle name"
                            value={name}
                            onChange={setName}
                            required
                            pattern=".*\S.*"
                            maxLength={100}
                        />
                        <Select
                            label="Phase for the new cycle"
                            value={phase}
                            onChange={setPhase}
                            options={phaseOptions(state)}
                        />
                        {!manual && (
                            <p className="cp-help">
                                The pattern resumes with the following cycle if
                                you choose a different phase.
                            </p>
                        )}
                    </>
                )}
                {manual ? (
                    <>
                        <p>
                            End the current cycle and start a new cycle in the
                            selected phase.
                        </p>
                        <p className="cp-help">
                            The selected phase becomes the campaign’s current
                            phase.
                        </p>
                    </>
                ) : (
                    <>
                        <p>
                            End <strong>{current.name}</strong> and cue the
                            post-cycle sequence for all {state.gangs.length}{" "}
                            gangs.
                        </p>
                        <div className="cp-transition">
                            <div>
                                <span className="cp-help">Ending</span>
                                <strong>{current.name}</strong>
                                <span>
                                    {M.getPhase(state, state.currentPhase).name}
                                </span>
                            </div>
                            <Icon icon={ArrowRight} />
                            <div>
                                <span className="cp-help">Starting</span>
                                <strong>
                                    {state.limit === null
                                        ? name
                                        : next?.name || "Campaign complete"}
                                </strong>
                                <span>
                                    {nextPhase?.name ||
                                        "Final post-cycle sequence"}
                                </span>
                            </div>
                        </div>
                        <p className="cp-help">
                            The post-cycle sequence is cued in the campaign log.
                            Player actions in that sequence are not automated by
                            this demo.
                        </p>
                    </>
                )}
                {state.limit === null && state.pattern && state.autoCycles && (
                    <CheckField
                        label="Skip next automatic change"
                        checked={skipAutomatic}
                        onChange={setSkipAutomatic}
                    />
                )}
                <FormFoot
                    onClose={close}
                    label={manual ? "End cycle" : "Confirm and end cycle"}
                />
            </form>
        </Modal>
    );
}
