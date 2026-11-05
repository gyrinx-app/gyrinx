import assert from "node:assert/strict";
import * as M from "./src/campaign-model.js";
import {
    defaultAutoCycles,
    nextAutomaticRun,
    validateAutoCycles,
    autoConfig,
} from "./src/campaign-clock.js";
let checks = 0;
function check(name, fn) {
    try {
        fn();
        checks++;
    } catch (error) {
        error.message = `${name}: ${error.message}`;
        throw error;
    }
}
const freshUnlimited = () => {
    const state = M.defaults();
    state.limit = null;
    return M.normalise(state);
};
const pattern = () => ({
    steps: [
        { phase: "occupation", cycles: 2 },
        { phase: "downtime", cycles: 1 },
        { phase: "takeover", cycles: 2 },
        { phase: "downtime", cycles: 1 },
    ],
    cursor: 0,
});
check("Fixed transitions and entry rewards", () => {
    const s = M.defaults();
    M.advance(s);
    assert.equal(s.currentPhase, "downtime");
    assert.equal(M.currentCycle(s).name, "Cycle 4");
    assert.ok(s.closedCycles.includes("c3"));
    assert.ok(s.cycles[2].endedAt);
    assert.equal(s.grants.length, 3);
    assert.deepEqual(
        s.gangs.map((g) => g.credits),
        [435, 370, 490],
    );
    M.advance(s);
    assert.equal(s.currentPhase, "takeover");
    assert.equal(s.grants.length, 3);
    M.moveCycle(s, s.currentCycle, "downtime");
    assert.equal(s.grants.length, 6);
    M.enterPhase(s, "downtime");
    assert.equal(s.grants.length, 6);
});
check("Consecutive cycles do not duplicate entry rewards", () => {
    const s = freshUnlimited();
    M.newCycle(s, "downtime");
    M.newCycle(s, "downtime");
    assert.equal(s.grants.length, 3);
    M.newCycle(s, "occupation");
    M.newCycle(s, "downtime");
    assert.equal(s.grants.length, 6);
});
check("Repeating pattern and names persist", () => {
    const s = freshUnlimited();
    s.pattern = pattern();
    for (const phase of [
        "occupation",
        "occupation",
        "downtime",
        "takeover",
        "takeover",
        "downtime",
        "occupation",
    ]) {
        const n = s.cycles.length;
        M.advance(s, `Round ${n + 1}`);
        assert.equal(s.currentPhase, phase);
        assert.equal(s.cycles.length, n + 1);
        assert.equal(M.currentCycle(s).name, `Round ${n + 1}`);
        assert.equal(s.cycles.at(-1).id, s.currentCycle);
    }
    assert.equal(s.grants.length, 6);
    assert.equal(s.pattern.cursor, 1);
    assert.ok(s.phases.every((p) => !M.phaseCompleted(s, p.id)));
    assert.deepEqual(M.normalise(structuredClone(s)), s);
});
check(
    "Pattern overrides consume one position and then resume the cadence",
    () => {
        const s = freshUnlimited();
        s.pattern = pattern();
        M.endCycle(s, { phase: "downtime", name: "One-off respite" });
        assert.equal(s.currentPhase, "downtime");
        assert.equal(s.pattern.cursor, 1);
        assert.equal(s.grants.length, 3);
        assert.equal(M.currentCycle(s).name, "One-off respite");
        M.endCycle(s);
        assert.equal(s.currentPhase, "occupation");
        assert.equal(s.pattern.cursor, 2);
        M.endCycle(s);
        assert.equal(s.currentPhase, "downtime");
        assert.equal(s.grants.length, 6);
        M.endCycle(s, { phase: "downtime" });
        assert.equal(
            s.grants.length,
            6,
            "Consecutive Downtime does not re-award entry credits",
        );
        assert.equal(s.pattern.cursor, 4);
        M.endCycle(s);
        assert.equal(s.currentPhase, "takeover");
        const before = structuredClone(s);
        assert.throws(() => M.endCycle(s, { phase: "missing" }));
        assert.deepEqual(s, before);
    },
);
check(
    "Ended campaigns reject transitions without mutation and reopen consistently",
    () => {
        const s = M.defaults();
        for (let i = 0; i < 5; i++) M.advance(s);
        assert.equal(s.ended, true);
        const before = structuredClone(s);
        assert.throws(() => M.advance(s));
        assert.deepEqual(s, before);
        M.reopenCampaign(s);
        assert.equal(s.ended, false);
        assert.ok(!s.closedCycles.includes(s.currentCycle));
        assert.equal(M.currentCycle(s).endedAt, undefined);
        M.moveCycle(s, s.currentCycle, "occupation");
        assert.equal(s.currentPhase, "occupation");
        const u = freshUnlimited();
        u.ended = true;
        const saved = structuredClone(u);
        assert.throws(() => M.newCycle(u, "occupation"));
        assert.deepEqual(u, saved);
    },
);
check("Completed phases can receive future cycles", () => {
    const s = M.defaults();
    M.advance(s);
    assert.ok(M.phaseCompleted(s, "occupation"));
    const current = s.currentCycle,
        id = M.insertCycle(s, "occupation");
    assert.equal(s.currentCycle, current);
    assert.equal(s.cycles[4].id, id);
    assert.equal(s.limit, 8);
    assert.equal(M.phaseCompleted(s, "occupation"), false);
    assert.equal(s.grants.length, 3);
    const before = structuredClone(s);
    assert.throws(() => M.insertCycle(s, "missing"));
    assert.deepEqual(s, before);
});
check("Preview and drop use the same position", () => {
    const s = M.defaults(),
        position = M.cycleDropPosition(s, "c7", "downtime", "c4");
    assert.deepEqual(position, { valid: true, index: 3, before: "c4" });
    M.moveCycle(s, "c7", "downtime", "c4");
    assert.equal(s.cycles[3].id, "c7");
    assert.equal(s.cycles[3].phase, "downtime");
    assert.equal(M.cycleDropPosition(s, "c2", "takeover").valid, false);
    assert.equal(M.cycleDropPosition(s, "c6", "downtime", "c1").valid, false);
    assert.deepEqual(
        s.cycles.map((c) => c.number),
        [1, 2, 3, 4, 5, 6, 7],
    );
});
check("Cycle edits retain phase history and battle snapshots", () => {
    const s = M.defaults(),
        battle = structuredClone(s.battles[0]);
    M.saveCycle(s, {
        ...M.currentCycle(s),
        name: "Last occupation",
        phase: "downtime",
    });
    assert.deepEqual(M.currentCycle(s).phaseHistory, [
        "occupation",
        "downtime",
    ]);
    M.saveCycle(s, { ...M.currentCycle(s), effects: "Fog" });
    assert.deepEqual(M.currentCycle(s).phaseHistory, [
        "occupation",
        "downtime",
    ]);
    assert.deepEqual(s.battles[0], battle);
    assert.equal(s.currentPhase, "downtime");
    assert.equal(s.grants.length, 3);
});
check("Duplication and phase ordering keep independent settings", () => {
    const s = M.defaults(),
        id = M.duplicatePhase(s, "downtime"),
        clone = M.getPhase(s, id);
    assert.equal(clone.name, "Downtime (copy)");
    clone.rewards.win.credits = "99";
    assert.equal(M.getPhase(s, "downtime").rewards.win.credits, "0");
    assert.equal(M.canRemovePhase(s, id), true);
    M.reorderPhase(s, id, 1);
    assert.equal(s.currentCycle, "c3");
    assert.equal(s.cycles[0].id, "c1");
    M.removePhase(s, id);
    assert.ok(!s.phases.some((p) => p.id === id));
});
check(
    "Deletion protects battles and preserves current cycle and numbering",
    () => {
        const s = M.defaults();
        assert.throws(() => M.deleteCycle(s, "c2"));
        s.battles = s.battles.filter((b) => b.cycle !== "c1");
        M.deleteCycle(s, "c1");
        assert.equal(s.currentCycle, "c3");
        assert.equal(M.currentCycle(s).number, 2);
        assert.equal(s.limit, 6);
        assert.deepEqual(
            s.cycles.map((c) => c.number),
            [1, 2, 3, 4, 5, 6],
        );
    },
);
check(
    "Settings derive fixed length and preserve pattern cursor when unchanged",
    () => {
        const s = freshUnlimited();
        M.saveSettings(s, {
            limit: null,
            start: "",
            days: 7,
            repeat: true,
            steps: pattern().steps,
        });
        M.advance(s);
        const cursor = s.pattern.cursor;
        M.saveSettings(s, {
            limit: null,
            start: "",
            days: 7,
            repeat: true,
            steps: pattern().steps,
        });
        assert.equal(s.pattern.cursor, cursor);
        M.saveSettings(s, {
            limit: 999,
            start: "",
            days: 7,
            repeat: false,
            steps: [],
        });
        assert.equal(s.limit, s.cycles.length);
        assert.equal(s.pattern, null);
        assert.throws(() =>
            M.saveSettings(s, {
                limit: null,
                start: "",
                days: 7,
                repeat: true,
                steps: [{ phase: "missing", cycles: 0 }],
            }),
        );
    },
);
check("Legacy migration is idempotent and retains occurred cycles", () => {
    const s = M.defaults();
    s.limit = null;
    s.mode = "manual";
    s.phaseEntries = ["occupation"];
    s.phases[0].length = 3;
    s.gangs[0].allowance = 50;
    s.battles.push({
        ...structuredClone(s.battles[0]),
        id: "future",
        cycle: "c7",
    });
    M.normalise(s);
    assert.equal(s.gangs[0].credits, 235);
    assert.equal(s.mode, undefined);
    assert.equal(s.phaseEntries, undefined);
    assert.equal(s.phases[0].length, undefined);
    assert.ok(s.closedCycles.includes("c7"));
    assert.equal(s.cycles.at(-1).id, s.currentCycle);
    assert.ok(s.removedSchedule.length);
    const before = structuredClone(s);
    M.normalise(s);
    assert.deepEqual(s, before);
    assert.throws(() => M.normalise({ ...M.defaults(), cycles: [] }));
});
check("Countdowns follow actual schedules and pattern cursor", () => {
    const s = M.defaults();
    assert.equal(M.phaseCountdown(s).cycles, 1);
    assert.equal(M.phaseCountdown(s).phase.id, "downtime");
    s.limit = null;
    M.normalise(s);
    s.pattern = pattern();
    assert.equal(M.phaseCountdown(s).cycles, 3);
    M.advance(s);
    assert.equal(M.phaseCountdown(s).cycles, 2);
    M.moveCycle(s, s.currentCycle, "takeover");
    assert.equal(M.phaseCountdown(s).cycles, 1);
    s.pattern = { steps: [{ phase: "takeover", cycles: 2 }], cursor: 0 };
    assert.equal(M.phaseCountdown(s), null);
});
check("Invalid battle input does not partially update gang ledgers", () => {
    const s = M.defaults(),
        data = {
            name: "Payouts",
            cycle: s.currentCycle,
            phase: s.currentPhase,
            participants: ["nightshade", "iron"],
            winner: "nightshade",
            sideJobs: [],
        };
    M.getPhase(s, s.currentPhase).rewards.loss.credits = "bad";
    const before = structuredClone(s);
    assert.throws(() => M.recordBattle(s, data));
    assert.deepEqual(s, before);
    assert.throws(() => M.recordBattle(s, { ...data, participants: [] }));
    assert.deepEqual(s, before);
});
check("Dates, formulas and invalid inputs remain safe", () => {
    const s = M.defaults();
    assert.equal(M.dates(s, M.currentCycle(s)), null);
    s.start = "2026-10-05";
    assert.equal(M.dates(s, M.currentCycle(s)), "19 Oct – 25 Oct");
    s.limit = null;
    assert.equal(M.dates(s, M.currentCycle(s)), null);
    assert.equal(M.endedDate("invalid"), "End date not recorded");
    assert.ok(M.rewardValid("2d6×10"));
    assert.ok(!M.rewardValid("arbitrary script"));
    assert.throws(() => M.savePhase(s, { ...s.phases[0], grant: -1 }));
});
check(
    "Deletion starts the replacement cycle with its own phase history",
    () => {
        const s = M.defaults();
        M.advance(s);
        M.deleteCycle(s, "c4");
        assert.equal(s.currentCycle, "c5");
        assert.deepEqual(M.currentCycle(s).phaseHistory, ["takeover"]);
    },
);
check(
    "Moving a default-named future cycle through Edit keeps its number and name aligned",
    () => {
        const s = M.defaults();
        M.saveCycle(s, { ...s.cycles[6], phase: "downtime" });
        const moved = s.cycles.find((c) => c.id === "c7");
        assert.equal(moved.name, `Cycle ${moved.number}`);
    },
);
check(
    "Repeated migration rejects malformed records without producing renderable invalid state",
    () => {
        const s = M.defaults();
        s.phases[0].rewards = null;
        assert.throws(() => M.normalise(s));
    },
);
check(
    "Malformed authored text and battle references are rejected before rendering",
    () => {
        const s = M.defaults();
        s.cycles[0].description = { unexpected: true };
        assert.throws(() => M.normalise(s));
        const b = M.defaults();
        b.battles[0].participants[0] = "missing";
        assert.throws(() => M.normalise(b));
    },
);
check("Calendar cadence, month ends and daylight-saving boundaries", () => {
    const config = { ...defaultAutoCycles(), weeks: 3, time: "10:00" };
    const first = nextAutomaticRun(config, Date.parse("2026-10-24T12:00:00Z"));
    assert.equal(first, "2026-10-26T16:00:00.000Z");
    assert.equal(
        nextAutomaticRun(config, Date.parse(first), Date.parse(first)),
        "2026-11-16T16:00:00.000Z",
    );
    const monthly = {
        ...config,
        frequency: "monthly",
        monthDay: 31,
        timeZone: "UTC",
    };
    const feb = nextAutomaticRun(
        monthly,
        Date.parse("2027-01-31T10:00:00Z"),
        Date.parse("2027-01-31T10:00:00Z"),
    );
    assert.equal(feb, "2027-02-28T10:00:00.000Z");
    assert.equal(
        nextAutomaticRun(monthly, Date.parse(feb), Date.parse(feb)),
        "2027-03-31T10:00:00.000Z",
    );
    const dst = {
        ...config,
        weeks: 1,
        weekday: 0,
        timeZone: "America/New_York",
        time: "02:30",
    };
    assert.equal(
        nextAutomaticRun(dst, Date.parse("2026-03-07T12:00:00Z")),
        "2026-03-08T07:30:00.000Z",
    );
    assert.equal(
        nextAutomaticRun(
            { ...dst, time: "01:30" },
            Date.parse("2026-10-31T12:00:00Z"),
        ),
        "2026-11-01T05:30:00.000Z",
    );
    for (const weeks of [0, -1, 1.5, 521, Number.MAX_SAFE_INTEGER])
        assert.throws(() => validateAutoCycles({ ...config, weeks }));
    assert.throws(() =>
        validateAutoCycles({ ...config, timeZone: "No/Such_Zone" }),
    );
    assert.equal(autoConfig({ ...config, frequency: "fortnightly" }).weeks, 2);
});
const automated = () => {
    const s = freshUnlimited();
    s.pattern = {
        steps: [
            { phase: "downtime", cycles: 1 },
            { phase: "occupation", cycles: 1 },
        ],
        cursor: 0,
    };
    s.autoCycles = {
        ...defaultAutoCycles(),
        nextAt: "2026-10-26T06:00:00.000Z",
    };
    return s;
};
check(
    "Automatic catch-up is idempotent and preserves actual dates and rewards",
    () => {
        const s = automated(),
            due = Date.parse(s.autoCycles.nextAt);
        assert.equal(M.runDueCycles(s, due - 1), 0);
        assert.equal(M.runDueCycles(s, due), 1);
        assert.equal(M.currentCycle(s).startedAt, "2026-10-26T06:00:00.000Z");
        assert.equal(s.cycles.at(-2).endedAt, M.currentCycle(s).startedAt);
        assert.equal(s.grants.length, 3);
        assert.equal(M.runDueCycles(s, due), 0);
        assert.equal(M.runDueCycles(s, Date.parse("2026-11-09T06:00:00Z")), 2);
        assert.equal(s.grants.length, 6);
        assert.equal(s.pattern.cursor, 1);
        assert.equal(
            M.normalise(structuredClone(s)).autoCycles.nextAt,
            s.autoCycles.nextAt,
        );
        s.ended = true;
        assert.equal(M.runDueCycles(s, Date.parse("2026-12-01T00:00:00Z")), 0);
        s.ended = false;
        s.status = "pre_campaign";
        assert.equal(M.runDueCycles(s, Date.parse("2026-12-01T00:00:00Z")), 0);
    },
);
check(
    "Manual ending can skip one automatic boundary without extra transitions",
    () => {
        const s = automated(),
            due = s.autoCycles.nextAt;
        M.endCycle(s, { skipAutomatic: true });
        assert.equal(s.cycles.length, 4);
        assert.equal(s.grants.length, 3);
        assert.equal(s.autoCycles.nextAt, "2026-11-02T06:00:00.000Z");
        assert.equal(M.runDueCycles(s, Date.parse(due)), 0);
        M.endCycle(s);
        assert.equal(s.autoCycles.nextAt, "2026-11-02T06:00:00.000Z");
        const fixed = M.defaults(),
            before = structuredClone(fixed);
        assert.throws(() => M.endCycle(fixed, { skipAutomatic: true }));
        assert.deepEqual(fixed, before);
    },
);
check("Catch-up yields after a bounded batch", () => {
    const s = automated();
    s.autoCycles.nextAt = "2020-01-06T06:00:00.000Z";
    const now = Date.parse("2026-10-24T12:00:00Z");
    assert.equal(M.runDueCycles(s, now), 100);
    assert.ok(Date.parse(s.autoCycles.nextAt) <= now);
    while (M.runDueCycles(s, now)) {
        /* Drain subsequent batches. */
    }
    assert.ok(Date.parse(s.autoCycles.nextAt) > now);
});
check("Cycle start labels never substitute indicative planning dates", () => {
    const s = M.defaults(),
        c = M.currentCycle(s);
    c.startedAt = "2026-10-20T06:00:00.000Z";
    assert.equal(M.cycleStartedDate(s, c), "Started 20 Oct 2026");
    delete c.startedAt;
    s.cycles[1].endedAt = "2026-10-19T06:00:00.000Z";
    assert.equal(M.cycleStartedDate(s, c), "Started 19 Oct 2026");
    delete s.cycles[1].endedAt;
    s.start = "2026-01-01";
    assert.equal(M.cycleStartedDate(s, c), null);
});
check(
    "Planning dates reject calendar rollover before mutating the schedule",
    () => {
        const s = M.defaults(),
            before = structuredClone(s);
        assert.throws(() =>
            M.saveSettings(s, { limit: s.limit, days: 7, start: "2026-02-31" }),
        );
        assert.deepEqual(s, before);
        assert.throws(() => M.normalise({ ...s, start: "2026-02-31" }));
    },
);
console.log(`Campaign model checks passed (${checks} groups).`);
