import * as M from "./history-model.js";
import { base } from "./history-format.js";
const { seed, version, addActivity, undo, restore } = M;
const copy = structuredClone;
// One-time reset of this demo's primary gang, requested for a fresh test run.
export const DEMO_RESET_KEY = "gyrinx-history-reset-2026-10-22-founding";
export function resetExampleGang(root) {
    const fresh = seed();
    fresh.versions = fresh.versions.slice(0, 1);
    fresh.head = fresh.versions[0].id;
    fresh.highlightsByOwner = {};
    fresh.highlights = [];
    fresh.otherHistories = copy(root.otherHistories || fresh.otherHistories);
    fresh.clones = copy(root.clones || []);
    fresh.campaignRolls = copy(root.campaignRolls || []);
    return fresh;
}

export const DEMO_POPULATE_KEY = "gyrinx-history-sample-week-2026-10-22";
export function populateExampleGang(root) {
    let state = copy(root);
    const start = Date.parse("2026-10-17T16:00:00Z");
    const previousEnd = Math.max(
        ...[...state.versions, ...state.journal].map((e) => Date.parse(e.when)),
    );
    if (previousEnd >= start)
        shiftDemoDates(state, start - 3600000 - previousEnd, () => true);
    const firstSampleIndex = state.versions.length;
    let day = 0,
        step = 0;
    function apply(change) {
        const oldVersions = state.versions.length,
            oldJournal = state.journal.length;
        state = change(state);
        const when = new Date(
            start + day * 86400000 + step++ * 1800000,
        ).toISOString();
        for (const event of [
            ...state.versions.slice(oldVersions),
            ...state.journal.slice(oldJournal),
        ])
            event.when = when;
    }
    const activity = (kind = "income") => apply((s) => addActivity(s, kind));
    activity();
    activity("armour");
    activity();
    apply(undo);
    day = 1;
    step = 0;
    activity();
    const retained = state.head;
    activity("armour");
    activity();
    apply(undo);
    apply(undo);
    day = 2;
    step = 0;
    activity();
    activity("armour");
    activity();
    day = 3;
    step = 0;
    activity("armour");
    apply(undo);
    activity();
    apply((s) => restore(s, retained));
    day = 4;
    step = 0;
    activity();
    activity("armour");
    apply(undo);
    activity();
    day = 5;
    step = 0;
    activity("armour");
    activity();
    activity();
    state.demoSampleStartId = state.versions[firstSampleIndex].id;
    state.demoSampleEndId = state.head;
    return state;
}

export const DEMO_DATES_KEY = "gyrinx-history-sample-dates-through-oct22";
function shiftDemoDates(state, delta, include) {
    for (const event of [...state.versions, ...state.journal])
        if (include(event))
            event.when = new Date(Date.parse(event.when) + delta).toISOString();
    for (const event of [...state.versions, ...state.journal]) {
        const target =
            event.type === "restore"
                ? version(state, event.restoreTarget || event.to)
                : event.type === "clone"
                  ? version(state, event.source)
                  : null;
        if (target) event.sourceWhen = target.when;
    }
}
export function dateExampleHistory(root) {
    const state = copy(root);
    let startIndex = state.versions.findIndex(
        (e) => e.id === state.demoSampleStartId,
    );
    if (startIndex < 0) {
        // Locate the original, untagged six-day demo without recreating its events.
        startIndex = state.versions.findIndex((event, i) => {
            const run = state.versions.slice(i, i + 18);
            return (
                run.length === 18 &&
                run[11].type === "restore" &&
                run[11].restoreTarget === run[3].id &&
                run[1].description === "Mesh armour bought for 15¢." &&
                run[17].description === "Battle income rolled."
            );
        });
    }
    if (startIndex < 0) return state;
    const first = state.versions[startIndex],
        last = state.versions[startIndex + 17];
    const delta = Date.parse("2026-10-17T16:00:00Z") - Date.parse(first.when);
    const prefixIds = new Set(
        state.versions.slice(0, startIndex + 18).map((e) => e.id),
    );
    shiftDemoDates(
        state,
        delta,
        (event) =>
            prefixIds.has(event.id) || (event.order || 0) <= (last.order || 0),
    );
    state.demoSampleStartId = first.id;
    state.demoSampleEndId = last.id;
    return state;
}

export function loadDemoHistory() {
    let state = M.seed();
    try {
        const saved = JSON.parse(localStorage.getItem(M.STORAGE_KEY));
        if (saved?.versions?.length && M.version(saved))
            state = M.hydrate(saved);
        if (!localStorage.getItem(DEMO_RESET_KEY)) {
            state = resetExampleGang(state);
            localStorage.setItem(M.STORAGE_KEY, JSON.stringify(state));
            localStorage.setItem(DEMO_RESET_KEY, "done");
            if (
                location.pathname === base ||
                location.pathname === `${base}gang/nightshade/`
            ) {
                const query = new URLSearchParams(location.search);
                query.delete("page");
                query.delete("entry");
                history.replaceState(
                    null,
                    "",
                    `${location.pathname}${query.size ? `?${query}` : ""}`,
                );
            }
        }
        if (!localStorage.getItem(DEMO_POPULATE_KEY)) {
            state = populateExampleGang(state);
            localStorage.setItem(M.STORAGE_KEY, JSON.stringify(state));
            localStorage.setItem(DEMO_POPULATE_KEY, "done");
        }
        if (!localStorage.getItem(DEMO_DATES_KEY)) {
            state = dateExampleHistory(state);
            localStorage.setItem(M.STORAGE_KEY, JSON.stringify(state));
            localStorage.setItem(DEMO_DATES_KEY, "done");
        }
    } catch {}
    const query = new URLSearchParams(location.search);
    const campaignTimeline =
        location.pathname === `${base}campaign/` &&
        query.get("view") === "timeline";
    if (query.has("page") || campaignTimeline) {
        query.delete("page");
        if (campaignTimeline) query.delete("view");
        history.replaceState(
            null,
            "",
            `${location.pathname}${query.size ? `?${query}` : ""}${location.hash}`,
        );
    }
    return state;
}
