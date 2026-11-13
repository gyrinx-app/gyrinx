import * as M from "./card-manager-model.js";

const defaults = { size: "standard", sideScroll: false, separateGroups: false };
export function readRosterView(raw) {
    try {
        const saved = JSON.parse(raw);
        if (
            saved &&
            ["small", "standard", "large"].includes(saved.size) &&
            typeof saved.sideScroll === "boolean" &&
            typeof saved.separateGroups === "boolean"
        )
            return {
                size: saved.size,
                sideScroll: saved.sideScroll,
                separateGroups: saved.separateGroups,
            };
    } catch {
        /* Unreadable preferences do not replace the saved roster. */
    }
    return { ...defaults };
}

export function rosterRows(saved, separate) {
    const visible = new Set(
        M.flatten(saved)
            .filter(
                (node) =>
                    !M.models[node.id].special && !M.isHidden(saved, node.id),
            )
            .map((node) => node.id),
    );
    if (!separate)
        return visible.size
            ? [
                  {
                      id: "all",
                      name: "Models",
                      ids: new Set(
                          M.flatten(saved)
                              .filter((node) => !M.models[node.id].special)
                              .map((node) => node.id),
                      ),
                  },
              ]
            : [];
    const rows = [];
    let run = null;
    for (const node of saved) {
        if (node.children) {
            run = null;
            const ids = new Set(
                node.children
                    .filter((child) => !M.models[child.id].special)
                    .map((child) => child.id),
            );
            if ([...ids].some((id) => visible.has(id)))
                rows.push({ ...node, ids });
        } else if (visible.has(node.id)) {
            if (!run) {
                run = {
                    id: `ungrouped-${node.id}`,
                    name: "Ungrouped models",
                    ids: new Set(),
                };
                rows.push(run);
            }
            run.ids.add(node.id);
        }
    }
    return rows;
}
