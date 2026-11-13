import assert from "node:assert/strict";
import * as M from "./src/card-manager-model.js";
import { rosterRows, readRosterView } from "./src/roster-view-model.js";

for (const raw of [
    null,
    "{",
    "[]",
    "null",
    "42",
    '{"size":"huge","sideScroll":true,"separateGroups":false}',
    '{"size":"small","sideScroll":1,"separateGroups":false}',
]) {
    assert.deepEqual(readRosterView(raw), {
        size: "standard",
        sideScroll: false,
        separateGroups: false,
    });
}
assert.deepEqual(
    readRosterView(
        '{"size":"large","sideScroll":true,"separateGroups":false,"extra":"discard"}',
    ),
    { size: "large", sideScroll: true, separateGroups: false },
);
const hidden = M.defaults().map((node) => ({ ...node, hidden: true }));
assert.deepEqual(rosterRows(hidden, false), []);
assert.deepEqual(rosterRows(hidden, true), []);
const layout = [
    { id: "nyx", pin: null },
    {
        id: "hidden",
        name: "Hidden group",
        hidden: true,
        children: [{ id: "ash", pin: null }],
    },
    { id: "rook", pin: null },
    {
        id: "front",
        name: "Front",
        children: [
            { id: "vesper", pin: null },
            { id: "jade", pin: null, hidden: true },
        ],
    },
    { id: "echo", pin: null },
];
assert.deepEqual(
    rosterRows(layout, true).map((row) => row.id),
    ["ungrouped-nyx", "ungrouped-rook", "front", "ungrouped-echo"],
);
assert(
    rosterRows(layout, true)[2].ids.has("jade"),
    "Hidden siblings keep their identity within a visible group.",
);
assert(
    rosterRows(layout, false)[0].ids.has("ash"),
    "Hidden cards remain available to the mounted continuous row.",
);
console.log(
    "Roster model passed: invalid settings, normalised preferences, all-hidden models and ordered hidden-group boundaries.",
);
