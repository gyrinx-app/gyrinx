export const models = {
    stash: { name: "Gang stash", special: true, icon: "stash" },
    actions: { name: "Available actions", special: true, icon: "actions" },
    campaign: { name: "Campaign attributes", special: true, icon: "campaign" },
    vesper: {
        name: "Vesper Krail",
        type: "Queen",
        subtypes: ["Leader"],
        rank: 0,
        rating: 245,
        pets: ["Phyrr cat", "Phyrr cat"],
        gear: "Plasma pistol · Shock whip",
    },
    nyx: {
        name: "Nyx",
        type: "Matriarch",
        rank: 1,
        rating: 195,
        gear: "Needle rifle · Stiletto knife",
    },
    ash: {
        name: "Ash",
        type: "Death-maiden",
        rank: 1,
        rating: 205,
        gear: "Venom claw · Needle pistol",
    },
    sera: {
        name: "Sera Vex",
        type: "Sister",
        rank: 2,
        rating: 115,
        gear: "Lasgun · Stiletto knife",
    },
    jade: {
        name: "Jade",
        type: "Sister",
        rank: 2,
        rating: 100,
        gear: "Shotgun · Fighting knife",
    },
    rook: {
        name: "Rook",
        type: "Sister",
        rank: 2,
        rating: 95,
        gear: "Autogun · Fighting knife",
    },
    wren: {
        name: "Wren, Last Daughter of the Thirteen Ashen Spires",
        type: "Wyld runner",
        rank: 3,
        rating: 100,
        pets: ["Phelynx"],
        gear: "Bow · Whip",
    },
    echo: {
        name: "Echo",
        type: "Little sister",
        rank: 4,
        rating: 55,
        gear: "Stub gun · Fighting knife",
    },
    violet: {
        name: "Violet",
        type: "Sister",
        rank: 2,
        rating: 90,
        status: "Dead",
        gear: "Lasgun",
    },
    crawler: {
        name: "Ash crawler",
        type: "Cargo-8 Ridgehauler",
        subtypes: ["Vehicle"],
        rank: 5,
        rating: 180,
        status: "Destroyed",
        gear: "Heavy stubber",
    },
};
const leaf = (id) => ({ id, pin: null });
export function defaults() {
    return [
        {
            id: "special",
            name: "Gang panels",
            pin: "top",
            colour: "ink",
            children: ["campaign", "actions", "stash"].map(leaf),
        },
        ...["vesper", "nyx", "ash", "sera", "jade", "rook", "wren", "echo"].map(
            leaf,
        ),
        {
            id: "fallen",
            name: "Dead / destroyed",
            pin: "bottom",
            colour: "ink",
            children: ["violet", "crawler"].map(leaf),
        },
    ];
}
export const copy = (value) => structuredClone(value);
export const flatten = (nodes) =>
    nodes.flatMap((n) => (n.children ? n.children : [n]));
export const find = (nodes, id) =>
    nodes.find((n) => n.id === id) || flatten(nodes).find((n) => n.id === id);
export function effectivePin(nodes, id) {
    const parent = nodes.find((n) => n.children?.some((c) => c.id === id));
    return parent?.pin || find(nodes, id)?.pin || null;
}
export function selectedIds(nodes, selection) {
    return nodes.flatMap((n) =>
        selection.includes(n.id)
            ? [n.id]
            : (n.children || [])
                  .filter((c) => selection.includes(c.id))
                  .map((c) => c.id),
    );
}
export function selectedModels(nodes, selection) {
    return selectedIds(nodes, selection)
        .flatMap((id) => {
            const n = find(nodes, id);
            return n.children || [n];
        })
        .filter((n) => !models[n.id].special);
}
export function clean(nodes) {
    return nodes
        .filter((n) => !n.children || n.children.length)
        .map((n) =>
            n.children
                ? {
                      ...n,
                      children: [...n.children].sort(
                          (a, b) => pinRank(a.pin) - pinRank(b.pin),
                      ),
                  }
                : n,
        )
        .sort((a, b) => pinRank(a.pin) - pinRank(b.pin));
}
const pinRank = (pin) => (pin === "top" ? 0 : pin === "bottom" ? 2 : 1);
export function remove(nodes, ids) {
    return clean(
        nodes
            .filter((n) => !ids.includes(n.id))
            .map((n) =>
                n.children
                    ? {
                          ...n,
                          children: n.children.filter(
                              (c) => !ids.includes(c.id),
                          ),
                      }
                    : n,
            ),
    );
}
export function move(nodes, selection, direction) {
    const result = copy(nodes);
    const swap = (list) => {
        const indexes = list.map((_, i) => i);
        if (direction > 0) indexes.reverse();
        indexes.forEach((i) => {
            const j = i + direction;
            if (
                selection.includes(list[i]?.id) &&
                list[j] &&
                !selection.includes(list[j].id) &&
                (list[i].pin || null) === (list[j].pin || null)
            )
                [list[i], list[j]] = [list[j], list[i]];
        });
    };
    result.forEach((n) => {
        if (n.children && !selection.includes(n.id)) swap(n.children);
    });
    swap(result);
    return result;
}
export function canRelocate(nodes, selection, targetId) {
    const ids = selectedIds(nodes, selection),
        target = find(nodes, targetId);
    if (
        !target ||
        !ids.length ||
        ids.includes(targetId) ||
        ids.some((id) =>
            find(nodes, id).children?.some((c) => c.id === targetId),
        )
    )
        return false;
    return ids.every(
        (id) =>
            nodes.some((group) => group.children?.some((c) => c.id === id)) ||
            effectivePin(nodes, id) === effectivePin(nodes, targetId),
    );
}
export function relocate(nodes, selection, targetId, mode = "before") {
    const ids = selectedIds(nodes, selection);
    const target = find(nodes, targetId);
    if (!canRelocate(nodes, selection, targetId)) return nodes;
    const pin = effectivePin(nodes, targetId);
    if (
        mode === "merge" &&
        ids.every((id) => target.children?.some((c) => c.id === id))
    )
        return nodes;
    const moved = ids.map((id) => ({
        ...copy(find(nodes, id)),
        pin: nodes.some((group) => group.children?.some((c) => c.id === id))
            ? null
            : effectivePin(nodes, id),
    }));
    let rest = remove(copy(nodes), ids);
    if (mode === "merge") {
        const children = [
            ...moved.flatMap((n) => n.children || [n]),
            ...((find(rest, targetId) || target).children || [target]),
        ].map((n) => ({ ...n, pin: null }));
        const group = target.children
            ? { ...target, children }
            : {
                  id: `group-${crypto.randomUUID()}`,
                  name: "Card group",
                  colour: "ink",
                  pin,
                  children,
              };
        const parent = rest.find((n) =>
            n.children?.some((c) => c.id === targetId),
        );
        if (parent) {
            parent.children = parent.children.flatMap((c) =>
                c.id === targetId ? children : [c],
            );
        } else rest = rest.map((n) => (n.id === targetId ? group : n));
    } else {
        const parent = rest.find((n) =>
            n.children?.some((c) => c.id === targetId),
        );
        // Dropping beside a group header moves outside it; beside a child moves inside it.
        const list = parent ? parent.children : rest;
        const foundIndex = list.findIndex((n) => n.id === targetId);
        const index =
            foundIndex < 0
                ? nodes.findIndex((n) => n.id === targetId)
                : foundIndex + (mode === "after" ? 1 : 0);
        list.splice(
            index,
            0,
            ...moved.flatMap((n) =>
                parent
                    ? (n.children || [n]).map((c) => ({
                          ...c,
                          pin:
                              nodes.find((g) =>
                                  g.children?.some(
                                      (child) => child.id === c.id,
                                  ),
                              )?.id === parent.id
                                  ? find(nodes, c.id).pin
                                  : null,
                      }))
                    : [n],
            ),
        );
    }
    return clean(rest);
}
export function profileCategory(id) {
    const model = models[id];
    if (model.special) return "Gang panels";
    if (["Dead", "Destroyed"].includes(model.status)) return "Dead / destroyed";
    return (
        model.subtypes?.[0] ||
        ["Leader", "Champion", "Ganger", "Prospect", "Juve", "Vehicle"][
            model.rank
        ]
    );
}
export function groupsAffectedByType(nodes, selection) {
    const picked = new Set(
        selectedIds(nodes, selection).flatMap((id) => {
            const n = find(nodes, id);
            return (n.children || [n]).map((c) => c.id);
        }),
    );
    return nodes.filter((n) => n.children?.some((c) => picked.has(c.id)));
}
export function groupByType(nodes, selection) {
    const picked = new Set(
        selectedIds(nodes, selection).flatMap((id) => {
            const n = find(nodes, id);
            return (n.children || [n]).map((c) => c.id);
        }),
    );
    if (!picked.size) return nodes;
    const affected = groupsAffectedByType(nodes, selection);
    const dissolved = nodes.flatMap((n) =>
        affected.some((g) => g.id === n.id)
            ? n.children.map((c) => ({
                  ...c,
                  pin: picked.has(c.id) ? null : n.pin || null,
              }))
            : [n],
    );
    const children = flatten(nodes)
        .filter((n) => picked.has(n.id))
        .map((n) => ({ ...copy(n), pin: null }));
    const buckets = new Map();
    children.forEach((n) => {
        const type = profileCategory(n.id);
        if (!buckets.has(type)) buckets.set(type, []);
        buckets.get(type).push(n);
    });
    const groups = [...buckets].map(([name, children]) => ({
        id: `group-${crypto.randomUUID()}`,
        name,
        children,
        colour: "ink",
        pin:
            name === "Gang panels"
                ? "top"
                : name === "Dead / destroyed"
                  ? "bottom"
                  : null,
    }));
    const first = dissolved.findIndex((n) => picked.has(n.id));
    const rest = remove(copy(dissolved), [...picked]);
    rest.splice(
        first < 0 ? rest.length : Math.min(first, rest.length),
        0,
        ...groups,
    );
    return clean(rest);
}
export function groupSelection(nodes, selection) {
    const ids = selectedIds(nodes, selection);
    if (!ids.length) return nodes;
    const pins = new Set(ids.map((id) => effectivePin(nodes, id)));
    if (pins.size !== 1) return nodes;
    const children = ids
        .flatMap((id) => {
            const n = find(nodes, id);
            return n.children || [n];
        })
        .map((n) => ({ ...copy(n), pin: null }));
    const first = nodes.findIndex(
        (n) =>
            ids.includes(n.id) || n.children?.some((c) => ids.includes(c.id)),
    );
    const rest = remove(copy(nodes), ids);
    rest.splice(Math.min(first, rest.length), 0, {
        id: `group-${crypto.randomUUID()}`,
        name: "Card group",
        colour: "ink",
        pin: [...pins][0],
        children,
    });
    return clean(rest);
}
export function ungroup(nodes, selection) {
    return clean(
        nodes.flatMap((n) =>
            n.children && selection.includes(n.id)
                ? n.children.map((c) => ({ ...c, pin: n.pin }))
                : [n],
        ),
    );
}
export function groupColour(colour) {
    return colour === "none"
        ? "var(--color-ink-400)"
        : `var(--color-${colour}-500)`;
}
export function groupActionIds(nodes, selection, clickedId) {
    const groups = nodes.filter(
        (n) =>
            n.children &&
            (selection.includes(n.id) ||
                n.children.every((child) => selection.includes(child.id))),
    );
    return groups.length > 1 && groups.some((n) => n.id === clickedId)
        ? groups.map((n) => n.id)
        : [clickedId];
}
export function setGroupBox(nodes, groupIds, showBox) {
    return nodes.map((n) =>
        n.children && groupIds.includes(n.id) ? { ...n, showBox } : n,
    );
}
export function setPin(nodes, selection, pin) {
    const ids = selectedIds(nodes, selection);
    return clean(
        copy(nodes).map((n) =>
            ids.includes(n.id)
                ? { ...n, pin }
                : n.children
                  ? {
                        ...n,
                        children: n.children.map((c) =>
                            ids.includes(c.id) ? { ...c, pin } : c,
                        ),
                    }
                  : n,
        ),
    );
}
const order = flatten(defaults()).map((n) => n.id);
export function sortCards(nodes, mode) {
    const compare = (a, b) => {
        const x = models[a.id],
            y = models[b.id];
        if (Boolean(x.special) !== Boolean(y.special))
            return x.special ? -1 : 1;
        if (x.special && y.special)
            return order.indexOf(a.id) - order.indexOf(b.id);
        if (mode === "default")
            return order.indexOf(a.id) - order.indexOf(b.id);
        if (mode === "profile")
            return x.rank - y.rank || order.indexOf(a.id) - order.indexOf(b.id);
        const [key, direction] = mode.split("-");
        return (
            (key === "name"
                ? x.name.localeCompare(y.name)
                : x.rating - y.rating) * (direction === "desc" ? -1 : 1)
        );
    };
    return copy(nodes)
        .map((n) =>
            n.children
                ? {
                      ...n,
                      children: n.children.sort(
                          (a, b) =>
                              pinRank(a.pin) - pinRank(b.pin) || compare(a, b),
                      ),
                  }
                : n,
        )
        .sort(
            (a, b) =>
                pinRank(a.pin) - pinRank(b.pin) ||
                compare(a.children?.[0] || a, b.children?.[0] || b),
        );
}

// Saved layouts are untrusted browser data, including values from older demos.
export function validLayout(value, colours) {
    if (!Array.isArray(value)) return false;
    const seen = new Set();
    const validPin = (pin) => pin === null || pin === "top" || pin === "bottom";
    const validId = (node) => {
        if (
            !node ||
            typeof node !== "object" ||
            Array.isArray(node) ||
            typeof node.id !== "string" ||
            seen.has(node.id) ||
            !validPin(node.pin)
        )
            return false;
        seen.add(node.id);
        return true;
    };
    return value.every((node) => {
        if (!validId(node)) return false;
        if (Object.hasOwn(node, "children")) {
            return (
                !Object.hasOwn(models, node.id) &&
                typeof node.name === "string" &&
                node.name.trim().length > 0 &&
                node.name.length <= 120 &&
                (node.colour === "none" || colours.includes(node.colour)) &&
                (!Object.hasOwn(node, "showBox") ||
                    typeof node.showBox === "boolean") &&
                Array.isArray(node.children) &&
                node.children.length > 0 &&
                node.children.every(
                    (child) =>
                        validId(child) &&
                        !Object.hasOwn(child, "children") &&
                        Object.hasOwn(models, child.id),
                )
            );
        }
        return Object.hasOwn(models, node.id);
    });
}
export const STORAGE_KEY = "gyrinx-card-manager-v1";
export function loadLayout(storage, colours) {
    try {
        const raw = storage().getItem(STORAGE_KEY);
        if (raw === null)
            return { layout: defaults(), writable: true, notice: "" };
        const layout = JSON.parse(raw);
        if (validLayout(layout, colours))
            return { layout: clean(layout), writable: true, notice: "" };
        throw new Error("Invalid saved layout");
    } catch {
        return {
            layout: defaults(),
            writable: false,
            notice: "The saved layout could not be read. Changes will only last for this visit.",
        };
    }
}
export function storeLayout(storage, layout, writable) {
    if (!writable) return false;
    try {
        storage().setItem(STORAGE_KEY, JSON.stringify(layout));
        return true;
    } catch {
        return false;
    }
}
