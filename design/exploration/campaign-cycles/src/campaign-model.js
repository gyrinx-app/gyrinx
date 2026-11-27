import {
    defaults,
    outcomeLabels,
    storageKey,
    addPastExamples,
} from "./campaign-data.js";
export { defaults, outcomeLabels, storageKey };
const id = () => crypto.randomUUID();
import {
    autoConfig,
    validateAutoCycles,
    nextAutomaticRun,
} from "./campaign-clock.js";
export {
    defaultAutoCycles,
    autoConfig,
    automaticChangeLabel,
} from "./campaign-clock.js";

export function rewardValid(value) {
    return /^(?:\d{1,7}|(?:[1-9]\d?)?d(?:3|6)(?:[×x*](?:[1-9]\d{0,3}))?)$/i.test(
        String(value).replace(/\s/g, ""),
    );
}
export function roll(value) {
    const clean = String(value).replace(/\s/g, "");
    if (!rewardValid(clean))
        throw new Error("Use a number or a dice expression such as 2d6×10.");
    if (/^\d+$/.test(clean)) return { value: Number(clean), dice: [] };
    const [, n = "1", sides, multiplier = "1"] = clean.match(
        /^(\d*)d(3|6)(?:[×x*](\d+))?$/i,
    );
    const dice = Array.from({ length: Number(n || 1) }, () => {
        const a = new Uint32Array(1);
        crypto.getRandomValues(a);
        return 1 + Math.floor((a[0] / 4294967296) * Number(sides));
    });
    return {
        value: dice.reduce((a, b) => a + b, 0) * Number(multiplier),
        dice,
    };
}
export function note(state, text) {
    state.entries.unshift({ id: id(), text, cycle: state.currentCycle });
}
export function enterPhase(state, phaseId) {
    const phase = getPhase(state, phaseId),
        current = currentCycle(state),
        previous = state.currentPhase;
    if (previous === phaseId) return;
    current.phaseHistory ||= [previous];
    if (current.phaseHistory.at(-1) !== phaseId)
        current.phaseHistory.push(phaseId);
    state.currentPhase = phaseId;
    current.phase = phaseId;
    note(state, `${phase.name} began.`);
    if (phase.grant > 0) {
        for (const gang of state.gangs) {
            gang.credits += phase.grant;
            state.grants.push({
                id: id(),
                phase: phaseId,
                gang: gang.id,
                amount: phase.grant,
                kind: "stash",
                cycle: current.id,
            });
        }
        note(state, `${phase.grant}¢ stash grant recorded for each gang.`);
    }
}

function requireActive(state) {
    if (state.ended)
        throw new Error(
            "The campaign has ended. Reopen it before changing cycles.",
        );
}
export function currentCycle(state) {
    return state.cycles.find((c) => c.id === state.currentCycle);
}
export function campaignStatus(state) {
    const key = state.ended
        ? "post_campaign"
        : state.status === "pre_campaign"
          ? "pre_campaign"
          : "in_progress";
    return {
        key,
        label: {
            pre_campaign: "Pre-campaign",
            in_progress: "Active",
            post_campaign: "Post-campaign",
        }[key],
    };
}
export function getPhase(state, phaseId) {
    const phase = state.phases.find((p) => p.id === phaseId);
    if (!phase) throw new Error("Select a phase.");
    return phase;
}
function cycleName(value, number) {
    const name = value == null ? `Cycle ${number}` : String(value).trim();
    if (!name || name.length > 100)
        throw new Error("Enter a cycle name of 1–100 characters.");
    return name;
}
function createCycle(state, phaseId, number, name = null) {
    getPhase(state, phaseId);
    return {
        id: id(),
        number,
        name: cycleName(name, number),
        phase: phaseId,
        description: "",
        effects: "",
    };
}
function finishCurrent(state) {
    const cycle = currentCycle(state);
    if (!state.closedCycles.includes(cycle.id))
        state.closedCycles.push(cycle.id);
    cycle.endedAt = new Date().toISOString();
    note(
        state,
        `${cycle.name} ended. Post-cycle sequence is due for each gang.`,
    );
}
function startCycle(state, cycle) {
    state.status = "in_progress";
    state.currentCycle = cycle.id;
    cycle.startedAt = new Date().toISOString();
    cycle.phaseHistory = [cycle.phase];
    if (cycle.phase !== state.currentPhase) enterPhase(state, cycle.phase);
    else
        note(
            state,
            `${cycle.name} began. ${getPhase(state, state.currentPhase).name} continues.`,
        );
}
export function reopenCampaign(state) {
    if (!state.ended) return;
    state.ended = false;
    state.status = "in_progress";
    state.closedCycles = state.closedCycles.filter(
        (id) => id !== state.currentCycle,
    );
    delete currentCycle(state).endedAt;
    note(state, "Campaign reopened.");
}
export function recordBattle(state, data) {
    if (state.ended)
        throw new Error("Reopen the campaign before recording a battle.");
    if (
        typeof data.name !== "string" ||
        !data.name.trim() ||
        data.name.trim().length > 120
    )
        throw new Error("Enter a battle name of 1–120 characters.");
    const cycle = state.cycles.find((c) => c.id === data.cycle),
        phase = state.phases.find((p) => p.id === data.phase);
    if (!cycle || !phase) throw new Error("Select a cycle and a phase.");
    if (
        !Array.isArray(data.participants) ||
        data.participants.length !== 2 ||
        data.participants.some((id) => !state.gangs.some((g) => g.id === id))
    )
        throw new Error("Select two gangs in this campaign.");
    if (data.participants[0] === data.participants[1])
        throw new Error("Select two different gangs.");
    if (data.winner !== "draw" && !data.participants.includes(data.winner))
        throw new Error("Select a battle result for these gangs.");
    if (
        !Array.isArray(data.sideJobs) ||
        data.sideJobs.some((id) => !data.participants.includes(id))
    )
        throw new Error("Side jobs must belong to a participating gang.");
    const payouts = data.participants.map((gangId) => {
        const outcome =
            data.winner === "draw"
                ? "draw"
                : data.winner === gangId
                  ? "win"
                  : "loss";
        const reward = phase.rewards[outcome],
            base = roll(reward.credits),
            side = data.sideJobs.includes(gangId)
                ? roll(phase.rewards.sideJob.credits)
                : { value: 0, dice: [] };
        const reputation =
            Number(reward.reputation) +
            (data.sideJobs.includes(gangId)
                ? Number(phase.rewards.sideJob.reputation)
                : 0);
        return {
            gang: gangId,
            credits: base.value + side.value,
            reputation,
            rolls: [...base.dice, ...side.dice].join(", ") || "Fixed reward",
        };
    });
    for (const payout of payouts) {
        const gang = state.gangs.find((g) => g.id === payout.gang);
        gang.credits += payout.credits;
        gang.reputation += payout.reputation;
    }
    state.battles.unshift({
        ...data,
        name: data.name.trim(),
        id: id(),
        cycleName: cycle.name,
        phaseName: phase.name,
        rules: structuredClone(phase.rewards),
        effects: { phase: phase.effects, cycle: cycle.effects },
        payouts,
    });
    note(
        state,
        `${data.name.trim()} recorded in ${cycle.name} · ${phase.name}. Battle rewards added to gang stashes.`,
    );
}
function validPlanningDate(value) {
    if (value === "") return true;
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value))
        return false;
    const date = new Date(`${value}T12:00:00Z`);
    return (
        Number.isFinite(date.getTime()) &&
        date.toISOString().slice(0, 10) === value
    );
}
export function normalise(state) {
    state.start ??= "";
    state.days = Number(state.days ?? 7);
    if (
        !Number.isInteger(state.days) ||
        state.days < 1 ||
        state.days > 365 ||
        !validPlanningDate(state.start)
    )
        throw new Error("Saved cycle planning dates are invalid.");
    if (
        state.version !== 1 ||
        !Array.isArray(state.cycles) ||
        !state.cycles.length ||
        !Array.isArray(state.phases) ||
        !state.phases.length ||
        !currentCycle(state)
    )
        throw new Error("Saved campaign data is incomplete.");
    for (const phase of state.phases) {
        delete phase.grantKind;
        delete phase.length;
    }
    delete state.mode;
    delete state.allocation;
    delete state.phaseEntries;
    for (const key of ["closedCycles", "entries", "grants", "battles", "gangs"])
        if (!Array.isArray(state[key]))
            throw new Error("Saved campaign data is incomplete.");
    for (const group of [state.cycles, state.phases, state.gangs])
        if (
            group.some(
                (item) =>
                    !item ||
                    typeof item.id !== "string" ||
                    typeof item.name !== "string",
            ) ||
            new Set(group.map((item) => item.id)).size !== group.length
        )
            throw new Error(
                "Saved campaign data contains invalid or duplicate records.",
            );
    if (
        typeof state.name !== "string" ||
        state.gangs.length < 2 ||
        state.gangs.some(
            (g) =>
                !Number.isFinite(g.credits) || !Number.isFinite(g.reputation),
        )
    )
        throw new Error("Saved campaign data is incomplete.");
    for (const phase of state.phases)
        if (
            !Number.isFinite(phase.grant) ||
            phase.grant < 0 ||
            Object.keys(outcomeLabels).some(
                (key) =>
                    !phase.rewards?.[key] ||
                    !rewardValid(phase.rewards[key].credits) ||
                    !Number.isFinite(phase.rewards[key].reputation),
            )
        )
            throw new Error("Saved phase rewards are invalid.");
    if (
        state.battles.some(
            (b) =>
                !b ||
                typeof b.name !== "string" ||
                !Array.isArray(b.participants) ||
                b.participants.length !== 2 ||
                b.participants.some(
                    (id) => !state.gangs.some((g) => g.id === id),
                ) ||
                !Array.isArray(b.payouts) ||
                b.payouts.some(
                    (p) =>
                        !p ||
                        !state.gangs.some((g) => g.id === p.gang) ||
                        !Number.isFinite(p.credits) ||
                        !Number.isFinite(p.reputation),
                ),
        )
    )
        throw new Error("Saved battle data is incomplete.");
    if (state.entries.some((e) => !e || typeof e.text !== "string"))
        throw new Error("Saved campaign log is incomplete.");
    for (const item of [...state.phases, ...state.cycles])
        for (const field of ["description", "effects"]) {
            if (item[field] == null) item[field] = "";
            if (typeof item[field] !== "string")
                throw new Error("Saved descriptions must be text.");
        }
    getPhase(state, state.currentPhase);
    if (state.cycles.some((c) => !state.phases.some((p) => p.id === c.phase)))
        throw new Error("A saved cycle refers to a missing phase.");
    currentCycle(state).phase = state.currentPhase;
    if (!state.ended) {
        state.closedCycles = state.closedCycles.filter(
            (id) => id !== state.currentCycle,
        );
        delete currentCycle(state).endedAt;
    }
    if (state.pattern) {
        validatePattern(state, state.pattern.steps);
        const length = patternPhases(state).length;
        state.pattern.cursor =
            (((Number.isInteger(state.pattern.cursor)
                ? state.pattern.cursor
                : 0) %
                length) +
                length) %
            length;
    }
    for (const gang of state.gangs) {
        gang.credits = Number(gang.credits) + Number(gang.allowance || 0);
        delete gang.allowance;
    }
    const downtimePhase = state.phases.find((p) => p.id === "downtime");
    if (
        [
            "Use the recruitment allowance during this cycle’s post-cycle sequence. Add your own stash credits if you need them.",
            "Recover, recruit and re-equip. Each gang receives 250 credits in its stash when Downtime begins.",
        ].includes(downtimePhase?.effects)
    )
        downtimePhase.effects =
            "Recover, recruit and re-equip. Each gang receives 250 credits when Downtime begins.";
    delete state.notices;
    for (const battle of state.battles) delete battle.date;
    const occupationCycle = state.cycles.find((c) => c.id === "c3");
    if (
        occupationCycle?.description ===
        "Get your final Occupation battles in by Sunday. We will settle territory claims before Downtime."
    )
        occupationCycle.description =
            "Finish your Occupation battles and settle territory claims before Downtime.";
    for (const item of [...state.phases, ...state.cycles])
        delete item.communication;
    const downtime = state.cycles.find((c) => c.id === "c4");
    if (downtime?.name === "A week of respite") downtime.name = "Cycle 4";
    if (state.limit === null) trimUnlimited(state);
    else renumber(state);
    state.status = campaignStatus(state).key;
    if (state.autoCycles) {
        validateAutoCycles(state.autoCycles);
        state.autoCycles = {
            ...autoConfig(state.autoCycles),
            nextAt: state.autoCycles.nextAt,
        };
        if (!Number.isFinite(Date.parse(state.autoCycles.nextAt)))
            throw new Error("Saved automatic cycle timing is invalid.");
        if (state.limit !== null || !state.pattern) state.autoCycles = null;
    }
    return addPastExamples(state);
}
function renumber(state) {
    state.cycles.forEach((cycle, index) => {
        if (cycle.name === `Cycle ${cycle.number}`)
            cycle.name = `Cycle ${index + 1}`;
        cycle.number = index + 1;
    });
    if (state.limit !== null) state.limit = state.cycles.length;
}
export function insertCycle(state, phaseId) {
    requireActive(state);
    getPhase(state, phaseId);
    if (state.limit === null)
        throw new Error(
            "End the current cycle to create a cycle in an unlimited campaign.",
        );
    const phaseIndex = state.phases.findIndex((p) => p.id === phaseId);
    const currentIndex = state.cycles.findIndex(
        (c) => c.id === state.currentCycle,
    );
    let at =
        state.cycles.findLastIndex(
            (c) =>
                state.phases.findIndex((p) => p.id === c.phase) <= phaseIndex,
        ) + 1;
    at = Math.max(at, currentIndex + 1);
    const cycle = createCycle(state, phaseId, at + 1);
    // Renumber existing default names before assigning the new default name.
    state.cycles.splice(at, 0, { ...cycle, name: "" });
    renumber(state);
    state.cycles[at].name = `Cycle ${at + 1}`;
    return cycle.id;
}
export function moveCycle(state, cycleId, phaseId, beforeId = null) {
    if (!state.phases.some((p) => p.id === phaseId))
        throw new Error("Select a phase.");
    const from = state.cycles.findIndex((c) => c.id === cycleId);
    if (from < 0 || state.closedCycles.includes(cycleId))
        throw new Error("Completed cycles stay as recorded.");
    const cycle = state.cycles[from];
    if (cycleId === state.currentCycle) {
        if (state.currentPhase !== phaseId) enterPhase(state, phaseId);
        renumber(state);
        return;
    }
    if (beforeId === cycleId) return;
    const remaining = state.cycles.filter((c) => c.id !== cycleId);
    const position = cycleDropPosition(state, cycleId, phaseId, beforeId);
    if (!position.valid)
        throw new Error("Place upcoming cycles after the current cycle.");
    const at = position.index;
    cycle.phase = phaseId;
    remaining.splice(at, 0, cycle);
    state.cycles = remaining;
    renumber(state);
}
export function cycleDeleteReason(state, cycleId) {
    if (state.battles.some((b) => b.cycle === cycleId))
        return "This cycle has recorded battles. Keep it to preserve their campaign period.";
    if (state.cycles.length === 1)
        return "Keep at least one cycle in the campaign.";
    if (
        cycleId === state.currentCycle &&
        !state.cycles[state.cycles.findIndex((c) => c.id === cycleId) + 1]
    )
        return "Add a following cycle before deleting the current cycle.";
    return "";
}
export function deleteCycle(state, cycleId) {
    const reason = cycleDeleteReason(state, cycleId);
    if (reason) throw new Error(reason);
    const index = state.cycles.findIndex((c) => c.id === cycleId);
    const cycle = state.cycles[index];
    if (!cycle) throw new Error("Select a cycle.");
    const replacement = state.cycles[index + 1];
    state.cycles.splice(index, 1);
    state.closedCycles = state.closedCycles.filter((id) => id !== cycleId);
    // Keep log entries readable after the cycle is removed.
    for (const entry of state.entries)
        if (entry.cycle === cycleId) entry.cycleName = cycle.name;
    renumber(state);
    if (state.currentCycle === cycleId) startCycle(state, replacement);
    note(state, `${cycle.name} deleted from the schedule.`);
}
export function reorderPhase(state, phaseId, offset) {
    if (offset !== -1 && offset !== 1)
        throw new Error("Move a phase up or down one position.");
    const from = state.phases.findIndex((p) => p.id === phaseId),
        to = from + offset;
    if (from < 0 || to < 0 || to >= state.phases.length) return;
    [state.phases[from], state.phases[to]] = [
        state.phases[to],
        state.phases[from],
    ];
    const current = state.cycles.findIndex((c) => c.id === state.currentCycle);
    const future = state.cycles
        .slice(current + 1)
        .sort(
            (a, b) =>
                state.phases.findIndex((p) => p.id === a.phase) -
                state.phases.findIndex((p) => p.id === b.phase),
        );
    state.cycles = [...state.cycles.slice(0, current + 1), ...future];
    renumber(state);
}
export function newCycle(state, phaseId, name = null) {
    requireActive(state);
    if (state.limit !== null)
        throw new Error("New cycles are available for unlimited campaigns.");
    const validName = name == null ? null : cycleName(name, 0);
    getPhase(state, phaseId);
    trimUnlimited(state);
    const cycle = createCycle(
        state,
        phaseId,
        currentCycle(state).number + 1,
        validName,
    );
    finishCurrent(state);
    state.cycles.push(cycle);
    startCycle(state, cycle);
}
export function phaseCompleted(state, phaseId) {
    if (
        state.limit === null ||
        (!state.ended && state.currentPhase === phaseId)
    )
        return false;
    const cycles = state.cycles.filter((c) => c.phase === phaseId);
    return (
        cycles.length > 0 &&
        cycles.every((c) => state.closedCycles.includes(c.id))
    );
}
export function dates(state, cycle) {
    if (state.limit === null || !state.start || !state.days || !cycle)
        return null;
    const start = new Date(`${state.start}T12:00:00Z`);
    if (Number.isNaN(start.getTime())) return null;
    start.setUTCDate(start.getUTCDate() + (cycle.number - 1) * state.days);
    const end = new Date(start);
    end.setUTCDate(end.getUTCDate() + state.days - 1);
    const format = (d) =>
        d.toLocaleDateString("en-GB", {
            day: "numeric",
            month: "short",
            timeZone: "UTC",
        });
    return `${format(start)} – ${format(end)}`;
}

function trimUnlimited(state) {
    const currentIndex = state.cycles.findIndex(
        (c) => c.id === state.currentCycle,
    );
    const future = state.cycles.slice(currentIndex + 1);
    const occurred = future.filter(
        (c) =>
            state.closedCycles.includes(c.id) ||
            state.battles.some((b) => b.cycle === c.id),
    );
    const unused = future.filter((c) => !occurred.includes(c));
    // Preserve removed schedule data locally for recovery without keeping planned cycles in the campaign.
    if (unused.length)
        state.removedSchedule = [
            ...new Map(
                [...(state.removedSchedule || []), ...unused].map((c) => [
                    c.id,
                    c,
                ]),
            ).values(),
        ];
    for (const c of occurred)
        if (!state.closedCycles.includes(c.id)) state.closedCycles.push(c.id);
    state.cycles = [
        ...state.cycles.slice(0, currentIndex),
        ...occurred,
        state.cycles[currentIndex],
    ];
    state.cycles.at(-1).phase = state.currentPhase;
    renumber(state);
}
function patternPhases(state) {
    return (state.pattern?.steps || []).flatMap((step) =>
        Array.from({ length: step.cycles }, () => step.phase),
    );
}
export function nextPatternPhase(state) {
    const phases = patternPhases(state);
    return phases.length
        ? phases[(state.pattern.cursor || 0) % phases.length]
        : null;
}
export function nextCycle(state) {
    if (state.limit !== null)
        return state.cycles[
            state.cycles.findIndex((c) => c.id === state.currentCycle) + 1
        ];
    const phase = nextPatternPhase(state);
    const current = state.cycles.find((c) => c.id === state.currentCycle);
    return phase
        ? {
              name: `Cycle ${current.number + 1}`,
              number: current.number + 1,
              phase,
          }
        : null;
}
export function advance(state, name = null, phaseOverride = null) {
    requireActive(state);
    if (state.limit === null) {
        const phase =
            phaseOverride || nextPatternPhase(state) || state.currentPhase;
        newCycle(state, phase, name);
        if (state.pattern) {
            state.pattern.currentIndex = state.pattern.cursor || 0;
            state.pattern.cursor =
                ((state.pattern.cursor || 0) + 1) % patternPhases(state).length;
        }
        return;
    }
    const next = nextCycle(state);
    if (next) getPhase(state, next.phase);
    finishCurrent(state);
    if (next) startCycle(state, next);
    else {
        state.ended = true;
        state.status = "post_campaign";
        note(state, "The final cycle ended. The campaign is complete.");
    }
}
export function endCycle(
    state,
    { name = null, phase = null, skipAutomatic = false } = {},
) {
    let followingAutomatic = null;
    if (skipAutomatic) {
        if (state.limit !== null || !state.pattern || !state.autoCycles)
            throw new Error(
                "Skipping a change needs a repeating pattern and automatic timing.",
            );
        const due = Date.parse(state.autoCycles.nextAt);
        followingAutomatic = nextAutomaticRun(state.autoCycles, due, due);
    }
    if (state.limit === null && !state.pattern)
        newCycle(state, phase || state.currentPhase, name);
    else advance(state, name, phase);
    if (followingAutomatic) {
        state.autoCycles.nextAt = followingAutomatic;
        note(state, "The next automatic cycle change was skipped.");
    }
}
export function endCycleLabel(state) {
    return state.limit !== null && !nextCycle(state)
        ? "End campaign"
        : "End cycle";
}
export function endedDate(value) {
    if (!value || Number.isNaN(new Date(value).getTime()))
        return "End date not recorded";
    return (
        "Ended " +
        new Date(value).toLocaleDateString("en-GB", {
            day: "numeric",
            month: "short",
            year: "numeric",
            timeZone: "America/Mexico_City",
        })
    );
}
export function cycleStartedDate(state, cycle) {
    const index = state.cycles.findIndex((c) => c.id === cycle.id);
    const value = cycle.startedAt || state.cycles[index - 1]?.endedAt;
    if (!value || !Number.isFinite(Date.parse(value))) return null;
    return (
        "Started " +
        new Intl.DateTimeFormat("en-GB", {
            day: "numeric",
            month: "short",
            year: "numeric",
            timeZone: state.autoCycles?.timeZone || "America/Mexico_City",
        }).format(new Date(value))
    );
}
export function phaseEndedDate(state, phaseId) {
    const cycles = state.cycles.filter((c) => c.phase === phaseId);
    return endedDate(cycles.at(-1)?.endedAt);
}

export function duplicatePhase(state, phaseId) {
    const at = state.phases.findIndex((p) => p.id === phaseId);
    if (at < 0) throw new Error("Select a phase.");
    const source = state.phases[at];
    let n = 1,
        name;
    do {
        const suffix = n === 1 ? " (copy)" : ` (copy ${n})`;
        name = source.name.slice(0, 100 - suffix.length) + suffix;
        n++;
    } while (
        state.phases.some((p) => p.name.toLowerCase() === name.toLowerCase())
    );
    const phase = { ...structuredClone(source), id: id(), name };
    state.phases.splice(at + 1, 0, phase);
    note(state, `${source.name} duplicated as ${name}.`);
    return phase.id;
}
export function phaseCountdown(state) {
    if (state.ended) return null;
    if (state.limit !== null) {
        const current = state.cycles.findIndex(
            (c) => c.id === state.currentCycle,
        );
        for (let i = current + 1; i < state.cycles.length; i++)
            if (state.cycles[i].phase !== state.currentPhase)
                return {
                    cycles: i - current,
                    phase: state.phases.find(
                        (p) => p.id === state.cycles[i].phase,
                    ),
                };
        return null;
    }
    const pattern = patternPhases(state),
        cursor = state.pattern?.cursor || 0;
    for (let i = 0; i < pattern.length; i++) {
        const phase = pattern[(cursor + i) % pattern.length];
        if (phase !== state.currentPhase)
            return {
                cycles: i + 1,
                phase: state.phases.find((p) => p.id === phase),
            };
    }
    return null;
}

export function cycleDropPosition(state, cycleId, phaseId, beforeId = null) {
    const from = state.cycles.findIndex((c) => c.id === cycleId),
        current = state.cycles.findIndex((c) => c.id === state.currentCycle);
    if (
        from < 0 ||
        state.closedCycles.includes(cycleId) ||
        !state.phases.some((p) => p.id === phaseId)
    )
        return { valid: false };
    if (cycleId === state.currentCycle)
        return {
            valid: true,
            index: current,
            before:
                state.cycles.slice(current + 1).find((c) => c.phase === phaseId)
                    ?.id || null,
        };
    const remaining = state.cycles.filter((c) => c.id !== cycleId);
    if (beforeId === cycleId)
        return {
            valid: true,
            index: from,
            before:
                remaining.slice(from).find((c) => c.phase === phaseId)?.id ||
                null,
        };
    if (
        beforeId &&
        !remaining.some((c) => c.id === beforeId && c.phase === phaseId)
    )
        return { valid: false };
    const raw = beforeId
        ? remaining.findIndex((c) => c.id === beforeId)
        : Math.max(
              current + 1,
              remaining.findLastIndex(
                  (c) =>
                      state.phases.findIndex((p) => p.id === c.phase) <=
                      state.phases.findIndex((p) => p.id === phaseId),
              ) + 1,
          );
    if (raw <= current || raw < 0) return { valid: false };
    return {
        valid: true,
        index: raw,
        before:
            remaining.slice(raw).find((c) => c.phase === phaseId)?.id || null,
    };
}

function validatePattern(state, steps) {
    if (
        !Array.isArray(steps) ||
        !steps.length ||
        steps.some(
            (step) =>
                !Number.isInteger(step.cycles) ||
                step.cycles < 1 ||
                step.cycles > 100 ||
                !state.phases.some((p) => p.id === step.phase),
        )
    )
        throw new Error("Each pattern step needs a phase and 1–100 cycles.");
}
export function saveSettings(state, value) {
    const pattern =
        value.limit === null && value.repeat
            ? {
                  steps: structuredClone(value.steps),
                  cursor:
                      JSON.stringify(state.pattern?.steps) ===
                      JSON.stringify(value.steps)
                          ? state.pattern.cursor
                          : 0,
                  currentIndex:
                      JSON.stringify(state.pattern?.steps) ===
                      JSON.stringify(value.steps)
                          ? state.pattern.currentIndex
                          : null,
              }
            : null;
    if (pattern) validatePattern(state, pattern.steps);
    let autoCycles = null;
    if (pattern && value.autoChange) {
        const config = autoConfig(value.autoCycles);
        validateAutoCycles(config);
        autoCycles = {
            ...config,
            nextAt:
                state.autoCycles &&
                JSON.stringify(autoConfig(state.autoCycles)) ===
                    JSON.stringify(config)
                    ? state.autoCycles.nextAt
                    : nextAutomaticRun(config),
        };
    }
    if (
        !Number.isInteger(Number(value.days)) ||
        value.days < 1 ||
        value.days > 365
    )
        throw new Error("Choose 1–365 days per cycle.");
    if (!validPlanningDate(value.start))
        throw new Error("Choose a valid campaign start date.");
    state.limit = value.limit === null ? null : state.cycles.length;
    state.start = value.start;
    state.days = Number(value.days);
    state.pattern = pattern;
    state.autoCycles = autoCycles;
    if (state.limit === null) trimUnlimited(state);
    note(state, "Campaign schedule updated.");
}
export function runDueCycles(state, now = Date.now()) {
    if (
        !state.autoCycles ||
        !state.pattern ||
        state.limit !== null ||
        state.ended ||
        state.status === "pre_campaign"
    )
        return 0;
    let count = 0;
    // Catch up in bounded batches so a long-closed tab can yield to the browser.
    while (count < 100 && Date.parse(state.autoCycles.nextAt) <= now) {
        const due = state.autoCycles.nextAt;
        const previous = currentCycle(state);
        advance(state);
        previous.endedAt = due;
        currentCycle(state).startedAt = due;
        note(state, "Cycle changed automatically at its scheduled time.");
        state.autoCycles.nextAt = nextAutomaticRun(
            state.autoCycles,
            Date.parse(due),
            Date.parse(due),
        );
        count++;
    }
    return count;
}
export function savePhase(state, value) {
    const phase = getPhase(state, value.id),
        name = value.name.trim();
    if (!name || name.length > 100)
        throw new Error("Enter a phase name of 1–100 characters.");
    if (
        state.phases.some(
            (p) =>
                p.id !== value.id &&
                p.name.toLowerCase() === name.toLowerCase(),
        )
    )
        throw new Error("Choose a different phase name.");
    const grant = Number(value.grant);
    if (!Number.isInteger(grant) || grant < 0 || grant > 1000000)
        throw new Error("Enter 0–1,000,000 entry credits.");
    const rewards = Object.fromEntries(
        Object.keys(outcomeLabels).map((key) => {
            const reward = value.rewards[key],
                reputation = Number(reward?.reputation);
            if (
                !reward ||
                !rewardValid(reward.credits) ||
                !Number.isInteger(reputation) ||
                Math.abs(reputation) > 1000
            )
                throw new Error(
                    "Use valid credits and a reputation amount between -1000 and 1000.",
                );
            return [
                key,
                {
                    credits: String(reward.credits).replace(/\s/g, ""),
                    reputation,
                },
            ];
        }),
    );
    Object.assign(phase, {
        name,
        grant,
        rewards,
        description: value.description,
        effects: value.effects,
    });
    note(state, `${name} settings updated.`);
}
export function saveCycle(state, value) {
    const cycle = state.cycles.find((c) => c.id === value.id);
    if (!cycle) throw new Error("Select a cycle.");
    let name = cycleName(value.name, cycle.number);
    const defaultNameUnchanged =
        name === cycle.name && cycle.name === `Cycle ${cycle.number}`;
    getPhase(state, value.phase);
    if (cycle.phase !== value.phase) {
        if (state.closedCycles.includes(cycle.id))
            throw new Error(
                "A completed cycle keeps its phase. Choose a future cycle to change its phase.",
            );
        moveCycle(state, cycle.id, value.phase);
    }
    if (defaultNameUnchanged) name = `Cycle ${cycle.number}`;
    Object.assign(cycle, {
        name,
        description: value.description,
        effects: value.effects,
    });
    note(state, `${name} settings updated.`);
}
export function removePhase(state, phaseId) {
    getPhase(state, phaseId);
    if (!canRemovePhase(state, phaseId))
        throw new Error(
            "Keep phases used by the campaign, its battles or its pattern.",
        );
    state.phases = state.phases.filter((p) => p.id !== phaseId);
}
export function canRemovePhase(state, phaseId) {
    return (
        phaseId !== state.currentPhase &&
        !state.cycles.some(
            (c) => c.phase === phaseId || c.phaseHistory?.includes(phaseId),
        ) &&
        !state.battles.some((b) => b.phase === phaseId) &&
        !state.grants.some((g) => g.phase === phaseId) &&
        !state.pattern?.steps.some((step) => step.phase === phaseId)
    );
}
