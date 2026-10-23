// Versions form a tree. The journal retains every movement through that tree.
export const STORAGE_KEY = "gyrinx-history-demo-v1";
export const people = {
    louis: { name: "louis", badge: "guilder", badgeLabel: "Guilder supporter" },
    mira: { name: "mira", badge: "staff", badgeLabel: "Staff" },
};
export const gangs = {
    nightshade: {
        name: "Nightshade Coven",
        house: "Escher",
        colour: "violet",
        icon: "escher",
        owner: "louis",
    },
    iron: {
        name: "Iron Vultures",
        house: "Orlock",
        colour: "teal",
        icon: "orlock",
        owner: "mira",
    },
};
export const ironSnapshot = {
    name: "Iron Vultures",
    rating: 915,
    credits: 145,
    models: [
        {
            id: "rook",
            name: "Rook",
            profile: "Road Captain",
            status: "Active",
            equipment: ["Autogun"],
            skills: [],
        },
    ],
    stash: [],
    territories: ["Old Ruins"],
    notes: "",
};
const copy = (value) => structuredClone(value);
export const uid = () => crypto.randomUUID();
export const now = () => new Date().toISOString();
const date = (day, hour, minute) => `2026-10-${day}T${hour}:${minute}:00-06:00`;
const empty = {
    name: "Nightshade Coven",
    rating: 0,
    credits: 1000,
    models: [],
    stash: [],
    territories: [],
    notes: "",
};
export function seed() {
    let state = {
        gangId: "nightshade",
        owner: "louis",
        versions: [],
        head: null,
        journal: [],
        highlights: [],
        clones: [],
    };
    function add(id, time, description, category, mutate, extra = {}) {
        const snapshot = copy(current(state));
        mutate(snapshot);
        const version = {
            id,
            parent: state.head,
            when: time,
            actor: "louis",
            gang: "nightshade",
            description,
            category,
            snapshot,
            ...extra,
        };
        state.versions.push(version);
        state.head = id;
    }
    add(
        "v1",
        date("18", "18", "20"),
        "Gang founded with a 1,000¢ budget.",
        "gang",
        () => {},
        { outcome: "Joined The Ash Road campaign." },
    );
    add(
        "v2",
        date("18", "18", "24"),
        "Leader hired for 220¢.",
        "model",
        (s) => {
            s.rating += 220;
            s.credits -= 220;
            s.models.push({
                id: "vesper",
                name: "Vesper Krail",
                profile: "Queen",
                status: "Active",
                equipment: ["Lasgun", "Mesh armour"],
                skills: [],
            });
        },
        { model: "Vesper Krail", outcome: "Lasgun and mesh armour included." },
    );
    add(
        "v3",
        date("18", "18", "30"),
        "Champion hired for 170¢.",
        "model",
        (s) => {
            s.rating += 170;
            s.credits -= 170;
            s.models.push({
                id: "nyx",
                name: "Nyx",
                profile: "Matriarch",
                status: "Active",
                equipment: [],
                skills: [],
            });
        },
        { model: "Nyx" },
    );
    add(
        "v4",
        date("18", "18", "35"),
        "Fighters hired for 380¢.",
        "model",
        (s) => {
            s.rating += 380;
            s.credits -= 380;
            for (const name of ["Ash", "Sera", "Wren", "Echo"])
                s.models.push({
                    id: name.toLowerCase(),
                    name,
                    profile: "Sister",
                    status: "Active",
                    equipment: [],
                    skills: [],
                });
        },
        { outcome: "Ash, Sera, Wren and Echo added to the roster." },
    );
    add(
        "v5",
        date("19", "10", "12"),
        "Plasma pistol bought for 50¢.",
        "kit",
        (s) => {
            s.rating += 50;
            s.credits -= 50;
            s.models[0].equipment.push("Plasma pistol");
        },
        { model: "Vesper Krail" },
    );
    add(
        "v6",
        date("20", "19", "42"),
        "Battle income rolled.",
        "credits",
        (s) => {
            s.credits += 60;
        },
        {
            battle: "The Sump Crossing",
            dice: [4, 2],
            outcome: "60¢ added to the gang’s credits.",
        },
    );
    add(
        "v7",
        date("20", "19", "44"),
        "Lasting injury rolled.",
        "model",
        (s) => {
            s.models[2].status = "In recovery";
        },
        {
            model: "Ash",
            battle: "The Sump Crossing",
            dice: [3, 4],
            diceMode: "D66",
            outcome: "Ash entered recovery.",
        },
    );
    add(
        "v8",
        date("20", "19", "46"),
        "Territory claimed.",
        "gang",
        (s) => {
            s.territories.push("Sludge Sea");
        },
        {
            battle: "The Sump Crossing",
            outcome: "Sludge Sea added to the gang’s territories.",
        },
    );
    add(
        "v9",
        date("21", "10", "08"),
        "Skill selected.",
        "model",
        (s) => {
            s.models[1].skills.push("Spring Up");
        },
        { model: "Nyx", outcome: "Spring Up added." },
    );
    state.highlightsByOwner = { louis: ["v6"] };
    state.otherHistories = { iron: seedIron() };
    return state;
}
export function version(state, id = state.head) {
    return state.versions.find((v) => v.id === id);
}
export function current(state) {
    return state.head ? version(state).snapshot : empty;
}
export function ancestry(
    state,
    id = state.head,
    versions = new Map(state.versions.map((action) => [action.id, action])),
) {
    const ids = new Set();
    while (id) {
        ids.add(id);
        // The target supplies restored state; parent retains the undo destination.
        const action = versions.get(id);
        id = action?.type === "restore" ? action.restoreTarget : action?.parent;
    }
    return ids;
}
export function children(state) {
    return state.versions.filter((v) => v.parent === state.head);
}
function nextOrder(state) {
    return (
        Math.max(
            0,
            ...state.versions.map((e) => e.order || 0),
            ...state.journal.map((e) => e.order || 0),
        ) + 1
    );
}
// Reuse a single lookup when rendering/filtering a complete history.
export function historyIndex(state) {
    const versions = new Map(
        state.versions.map((action) => [action.id, action]),
    );
    const active = ancestry(state, state.head, versions),
        changes = new Map();
    const events = [
        ...state.versions.filter((e) => e.type === "restore"),
        ...state.journal,
    ].sort(
        (a, b) =>
            new Date(b.when) - new Date(a.when) ||
            (b.order || 0) - (a.order || 0),
    );
    for (const event of events)
        for (const id of event.affected || []) {
            if (!active.has(id) && !changes.has(id))
                changes.set(id, {
                    ...event,
                    type: event.undoReason || event.type,
                });
        }
    return { versions, active, changes };
}
export function status(state, id) {
    return historyIndex(state).changes.get(id) || null;
}
function move(state, to, type, time = now(), actor = ownerOf(state)) {
    assertOwner(state, actor);
    if (to === state.head) return state;
    if (to !== null && !version(state, to)) throw Error("Version not found.");
    const next = copy(state),
        before = ancestry(state),
        after = ancestry(state, to);
    const removed = [...before].filter((id) => !after.has(id));
    const restored = [...after].filter((id) => !before.has(id));
    const acted = version(state, type === "undo" ? state.head : to);
    next.journal.push({
        id: uid(),
        order: nextOrder(state),
        type,
        undoReason:
            type === "redo" && acted?.type === "restore" ? "restore" : type,
        when: time,
        actor,
        gang: state.gangId || "nightshade",
        from: state.head,
        to,
        affected: removed,
        restored,
        before: copy(current(state)),
        snapshot: copy(to ? version(state, to).snapshot : empty),
        description: type === "undo" ? "Action undone." : "Action redone.",
    });
    next.head = to;
    return next;
}
export function undo(state, actor = ownerOf(state)) {
    assertOwner(state, actor);
    const v = version(state);
    return v?.parent ? move(state, v.parent, "undo", now(), actor) : state;
}
export function redo(state, id, actor = ownerOf(state)) {
    assertOwner(state, actor);
    const candidates = children(state);
    const chosen = id ? candidates.find((v) => v.id === id) : candidates.at(-1);
    if (!chosen) return state;
    return move(state, chosen.id, "redo", now(), actor);
}
export function restore(
    state,
    id,
    actor = ownerOf(state),
    sourceWhen,
    sourceEntryId = id,
) {
    assertOwner(state, actor);
    const target = version(state, id);
    if (!target) throw Error("Version not found.");
    const next = copy(state),
        before = ancestry(state),
        after = ancestry(state, id);
    const affected = [...before].filter((pk) => !after.has(pk));
    const event = {
        id: uid(),
        order: nextOrder(state),
        type: "restore",
        parent: state.head,
        restoreTarget: id,
        targetEntryId: sourceEntryId,
        sourceWhen: sourceWhen || target.when,
        when: now(),
        actor,
        gang: state.gangId || "nightshade",
        category: "history",
        before: copy(current(state)),
        snapshot: copy(target.snapshot),
        affected,
        restored: [...after].filter((pk) => !before.has(pk)),
        description: `Restored their gang to the ${versionDate(sourceWhen || target.when)} version.`,
        outcome: `${affected.length} action${affected.length === 1 ? "" : "s"} undone; later history retained.`,
    };
    next.versions.push(event);
    next.head = event.id;
    return next;
}
export function highlight(state, id, viewer = ownerOf(state)) {
    assertOwner(state, viewer);
    const next = copy(state);
    const saved = next.highlightsByOwner?.[viewer] || next.highlights || [];
    next.highlightsByOwner = {
        ...next.highlightsByOwner,
        [viewer]: saved.includes(id)
            ? saved.filter((v) => v !== id)
            : [...saved, id],
    };
    return next;
}
export function isHighlighted(state, id, viewer) {
    if (viewer !== ownerOf(state)) return false;
    return (
        state.highlightsByOwner?.[viewer] ||
        state.highlights ||
        []
    ).includes(id);
}
export function addActivity(state, action, actor = ownerOf(state)) {
    assertOwner(state, actor);
    const next = copy(state),
        snapshot = copy(current(state));
    const data = {
        id: `v${next.versions.length + 1}`,
        order: nextOrder(state),
        parent: state.head,
        when: now(),
        actor,
        gang: state.gangId || "nightshade",
        category: "kit",
    };
    if (action === "armour") {
        if (snapshot.credits < 15)
            throw Error("The gang needs 15¢ to buy mesh armour.");
        snapshot.credits -= 15;
        snapshot.rating += 15;
        snapshot.stash.push("Mesh armour");
        Object.assign(data, {
            description: "Mesh armour bought for 15¢.",
            outcome: "Added to the stash.",
        });
    } else if (action === "income") {
        const dice = [
            1 + Math.floor(Math.random() * 6),
            1 + Math.floor(Math.random() * 6),
        ];
        const income = dice.reduce((a, b) => a + b, 0) * 10;
        snapshot.credits += income;
        Object.assign(data, {
            description: "Battle income rolled.",
            category: "credits",
            battle: "The Sump Crossing",
            dice,
            outcome: `${income}¢ added to the gang’s credits.`,
        });
    } else throw Error("Unknown action.");
    next.versions.push({ ...data, snapshot });
    next.head = data.id;
    return next;
}
export function cloneVersion(
    state,
    id,
    name,
    actor = ownerOf(state),
    sourceWhen,
) {
    assertOwner(state, actor);
    const source = version(state, id);
    if (!source) throw Error("Version not found.");
    const next = copy(state),
        cloneId = uid(),
        snapshot = copy(source.snapshot);
    snapshot.name = name.trim() || `${snapshot.name} (copy)`;
    const when = now();
    next.clones.push({
        id: cloneId,
        name: snapshot.name,
        gang: state.gangId || "nightshade",
        owner: actor,
        sourceWhen: sourceWhen || source.when,
        source: id,
        when,
        snapshot,
    });
    return next;
}
export const campaignEvents = [
    {
        id: "c1",
        when: date("18", "17", "00"),
        actor: "mira",
        description: "Campaign created.",
        category: "campaign",
        outcome: "The Ash Road is open to players.",
    },
    {
        id: "c2",
        when: date("20", "19", "41"),
        actor: "mira",
        gang: "iron",
        battle: "The Sump Crossing",
        description: "Battle result recorded.",
        category: "campaign",
        outcome: "Iron Vultures won against Nightshade Coven.",
    },
];
export function ownerOf(state) {
    return state.owner || gangs[state.gangId || "nightshade"].owner;
}
function assertOwner(state, actor) {
    if (ownerOf(state) !== actor)
        throw Error("Only the gang’s owner can change this history.");
}
export function versionDate(value) {
    return new Date(value).toLocaleString("en-GB", {
        timeZone: "America/Mexico_City",
        day: "numeric",
        month: "long",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
}
export function seedIron() {
    const start = copy(ironSnapshot);
    start.rating = 900;
    start.credits = 110;
    start.models[0].equipment = [];
    const bought = copy(start);
    bought.rating += 15;
    bought.credits -= 15;
    bought.models[0].equipment.push("Autogun");
    const after = copy(bought);
    after.credits += 50;
    return {
        gangId: "iron",
        owner: "mira",
        head: "iron-income",
        journal: [],
        clones: [],
        highlightsByOwner: { mira: ["iron-purchase"] },
        versions: [
            {
                id: "iron-founded",
                parent: null,
                when: date("18", "18", "22"),
                actor: "mira",
                gang: "iron",
                category: "gang",
                description: "Gang joined the campaign.",
                snapshot: start,
            },
            {
                id: "iron-purchase",
                parent: "iron-founded",
                when: date("21", "11", "18"),
                actor: "mira",
                gang: "iron",
                category: "kit",
                description: "Autogun bought for 15¢.",
                model: "Rook",
                outcome: "Added to Rook’s equipment.",
                snapshot: bought,
            },
            {
                id: "iron-income",
                parent: "iron-purchase",
                when: date("21", "11", "20"),
                actor: "mira",
                gang: "iron",
                category: "credits",
                description: "Territory income rolled.",
                dice: [5],
                outcome: "50¢ added to the gang’s credits.",
                snapshot: after,
            },
        ],
    };
}
function upgradeRestores(state) {
    const legacy = state.journal.filter((e) => e.type === "restore");
    if (!legacy.length) return;
    const savedHead = state.head,
        oldVersions = [...state.versions],
        oldJournal = [...state.journal];
    const events = [
        ...oldVersions.map((e) => ({ e, domain: true })),
        ...oldJournal.map((e) => ({ e, domain: false })),
    ]
        .map((item, index) => ({ ...item, index }))
        .sort(
            (a, b) =>
                new Date(a.e.when) - new Date(b.e.when) ||
                (a.e.order || 0) - (b.e.order || 0) ||
                a.index - b.index,
        );
    for (const e of legacy) {
        state.versions.push({
            ...e,
            parent: e.from,
            restoreTarget: e.to,
            targetEntryId: e.targetEntryId || e.to,
            sourceWhen: e.sourceWhen || version(state, e.to)?.when,
        });
    }
    state.journal = state.journal.filter((e) => e.type !== "restore");
    let cursor = null,
        oldCursor = null,
        order = 0;
    const aliases = new Map();
    for (const item of events) {
        const e = item.e;
        order++;
        if (item.domain) {
            const v = version(state, e.id);
            if (e.parent === oldCursor) v.parent = cursor;
            v.order = order;
            cursor = e.id;
            oldCursor = e.id;
        } else if (e.type === "restore") {
            const v = version(state, e.id);
            v.order = order;
            v.parent =
                e.from === oldCursor ? cursor : aliases.get(e.from) || e.from;
            const before = ancestry(state, v.parent),
                after = ancestry(state, v.restoreTarget);
            v.affected = [...before].filter((pk) => !after.has(pk));
            v.restored = [...after].filter((pk) => !before.has(pk));
            cursor = v.id;
            oldCursor = e.to;
            aliases.set(e.to, v.id);
        } else if (["undo", "redo"].includes(e.type)) {
            const oldTo = e.to;
            e.from =
                e.from === oldCursor ? cursor : aliases.get(e.from) || e.from;
            e.to = aliases.get(e.to) || e.to;
            e.order = order;
            const before = ancestry(state, e.from),
                after = ancestry(state, e.to);
            e.affected = [...before].filter((pk) => !after.has(pk));
            e.restored = [...after].filter((pk) => !before.has(pk));
            e.undoReason =
                e.type === "redo" && version(state, e.to)?.type === "restore"
                    ? "restore"
                    : e.type;
            cursor = e.to;
            oldCursor = oldTo;
        } else {
            e.order = order;
            if (e.to === oldCursor) e.to = cursor;
        }
    }
    state.head =
        savedHead === oldCursor ? cursor : aliases.get(savedHead) || savedHead;
}
export function hydrate(saved) {
    const state = copy(saved);
    state.gangId ||= "nightshade";
    state.owner ||= "louis";
    state.highlightsByOwner ||= { [state.owner]: state.highlights || [] };
    state.otherHistories ||= { iron: seedIron() };
    state.campaignRolls ||= [];
    upgradeRestores(state);
    for (const other of Object.values(state.otherHistories))
        upgradeRestores(other);
    return state;
}
export function historyFor(root, id = "nightshade") {
    return id === "nightshade" ? root : root.otherHistories?.[id];
}
export function updateGang(root, id, change) {
    if (id === "nightshade") return change(root);
    const next = copy(root);
    next.otherHistories[id] = change(historyFor(root, id));
    return next;
}
export function allClones(root) {
    return [
        ...root.clones,
        ...Object.values(root.otherHistories || {}).flatMap((s) => s.clones),
    ];
}
export function visibleEntries(state) {
    return [
        ...state.versions,
        ...state.journal.filter(
            (e) => !["undo", "redo", "clone"].includes(e.type),
        ),
    ].map((e) => {
        if (e.type !== "restore") return e;
        const target = version(state, e.restoreTarget || e.to);
        if (target)
            return {
                ...e,
                description: `Restored their gang to the ${versionDate(e.sourceWhen || target.when)} version.`,
            };
        return e;
    });
}
export function entries(state, campaign = false) {
    return [
        ...visibleEntries(state),
        ...(campaign
            ? [
                  ...Object.values(state.otherHistories || {}).flatMap(
                      visibleEntries,
                  ),
                  ...campaignEvents,
                  ...(state.campaignRolls || []),
              ]
            : []),
    ]
        .map((e, index) => ({ ...e, sequence: index }))
        .sort(
            (a, b) =>
                new Date(b.when) - new Date(a.when) ||
                (b.order || 0) - (a.order || 0) ||
                b.sequence - a.sequence,
        );
}
export function addRoll(
    state,
    {
        reason,
        count = 2,
        results,
        outcome = "",
        battle = "",
        actor = ownerOf(state),
    },
) {
    assertOwner(state, actor);
    if (!reason.trim()) throw Error("Enter a reason for this roll.");
    if (!Number.isInteger(count) || count < 1 || count > 10)
        throw Error("Choose between 1 and 10 dice.");
    const dice =
        results ||
        Array.from({ length: count }, () => 1 + Math.floor(Math.random() * 6));
    if (
        dice.length !== count ||
        dice.some((n) => !Number.isInteger(n) || n < 1 || n > 6)
    )
        throw Error("Enter one result from 1 to 6 for each die.");
    const next = copy(state),
        id = uid();
    next.versions.push({
        id,
        order: nextOrder(state),
        parent: state.head,
        when: now(),
        actor,
        gang: state.gangId || "nightshade",
        category: "dice",
        description: reason.trim(),
        dice,
        outcome: outcome.trim(),
        battle,
        snapshot: copy(current(state)),
    });
    next.head = id;
    return next;
}

// Reconstruct branches from the retained movement ledger, without changing history.
export function timelineGroups(state) {
    const { active, changes } = historyIndex(state);
    const groups = [];
    const events = [
        ...state.versions.filter((e) => e.type === "restore"),
        ...state.journal,
    ]
        .filter((e) => e.affected?.length)
        .sort(
            (a, b) =>
                new Date(a.when) - new Date(b.when) ||
                (a.order || 0) - (b.order || 0),
        );
    for (const event of events) {
        const ids = new Set(
            event.affected.filter(
                (id) => !active.has(id) && changes.get(id)?.id === event.id,
            ),
        );
        if (!ids.size) continue;
        const absorbed = groups.filter(
            (g) => ids.has(g.anchor) || ids.has(g.id),
        );
        for (const g of absorbed) groups.splice(groups.indexOf(g), 1);
        const nested =
            event.type === "restore" || event.undoReason === "restore";
        const children = nested
            ? absorbed
            : absorbed.flatMap((g) => g.children);
        if (!nested)
            for (const g of absorbed) for (const id of g.ids) ids.add(id);
        const oldest = state.versions
            .filter((v) => ids.has(v.id))
            .sort((a, b) => (a.order || 0) - (b.order || 0))[0];
        const anchor =
            oldest?.type === "restore" ? oldest.restoreTarget : oldest?.parent;
        groups.push({
            id: event.id,
            ids: [...ids],
            children,
            anchor,
            when: event.when,
        });
    }
    return groups;
}

export function generateDemoActions(state, count = 10, actor = ownerOf(state)) {
    let next = state;
    for (let i = 0; i < count; i++)
        next = addActivity(
            next,
            i % 3 === 2 && current(next).credits >= 15 ? "armour" : "income",
            actor,
        );
    return next;
}
