import { useId, useState } from "react";
import { Button, Field, Input, Switch, Table } from "../../ui";
import {
    ReorderScope,
    ReorderItem,
    ReorderDropLine,
    type ReorderSource,
    type ReorderDestination,
} from "../../ui/reorder";

type Entry = { id: string; name: string; note: string; locked?: boolean };
type Group = { id: string; name: string; locked?: boolean; entries: Entry[] };
type Destination =
    | { kind: "group"; afterId: string | null }
    | { kind: "entry"; groupId: string; afterId: string | null };

function example(): Group[] {
    return [
        {
            id: "recorded",
            name: "Recorded group",
            locked: true,
            entries: [
                {
                    id: "recorded-visit",
                    name: "Recorded visit",
                    note: "Keep this position",
                    locked: true,
                },
            ],
        },
        {
            id: "planned",
            name: "Planned group",
            entries: [
                { id: "market", name: "Market visit", note: "Bring supplies" },
                { id: "council", name: "Council visit", note: "Meet at noon" },
            ],
        },
        { id: "empty", name: "Optional group", entries: [] },
    ];
}

export function ReorderDemo() {
    const [groups, setGroups] = useState(example);
    const [readOnly, setReadOnly] = useState(false);
    const readOnlyId = useId();
    const [lastMove, setLastMove] = useState("No moves yet.");
    const targets: ReorderDestination[] = [];
    const destinations = new Map<string, Destination>();
    const groupBoundaries = groups
        .map((group) => "group-before-" + group.id)
        .concat("groups-end");
    const addTarget = (id: string, label: string, destination: Destination) => {
        targets.push({ id, label });
        destinations.set(id, destination);
    };
    groups.forEach((group, index) => {
        addTarget(groupBoundaries[index], "Before " + group.name, {
            kind: "group",
            afterId: groups[index - 1]?.id ?? null,
        });
        addTarget("entries-start-" + group.id, "Start of " + group.name, {
            kind: "entry",
            groupId: group.id,
            afterId: null,
        });
        group.entries.forEach((entry) =>
            addTarget(
                "entry-after-" + entry.id,
                "After " + entry.name + " in " + group.name,
                { kind: "entry", groupId: group.id, afterId: entry.id },
            ),
        );
    });
    addTarget("groups-end", "After the last group", {
        kind: "group",
        afterId: groups.at(-1)?.id ?? null,
    });
    const groupTargets = groupBoundaries.filter((_, index) => index > 0);
    const entryTargets = targets
        .filter((target) => {
            const destination = destinations.get(target.id);
            return (
                destination?.kind === "entry" &&
                !groups.find((group) => group.id === destination.groupId)
                    ?.locked
            );
        })
        .map((target) => target.id);
    const sources: ReorderSource[] = groups.flatMap((group, index) => [
        {
            id: "group-" + group.id,
            label: group.name,
            origin: groupBoundaries[index],
            targets: group.locked
                ? []
                : groupTargets.filter(
                      (id) =>
                          id !== groupBoundaries[index] &&
                          id !== groupBoundaries[index + 1],
                  ),
        },
        ...group.entries.map((entry, position) => ({
            id: "entry-" + entry.id,
            label: entry.name,
            origin: position
                ? "entry-after-" + group.entries[position - 1].id
                : "entries-start-" + group.id,
            targets:
                entry.locked || group.locked
                    ? []
                    : entryTargets.filter(
                          (id) =>
                              id !== "entry-after-" + entry.id &&
                              id !==
                                  (position
                                      ? "entry-after-" +
                                        group.entries[position - 1].id
                                      : "entries-start-" + group.id),
                      ),
        })),
    ]);
    function move(itemId: string, targetId: string) {
        const destination = destinations.get(targetId);
        const source = sources.find((source) => source.id === itemId);
        if (readOnly || !destination || !source?.targets.includes(targetId))
            return;
        setGroups((current) => {
            if (destination.kind === "group") {
                const selected = current.find(
                    (group) => "group-" + group.id === itemId,
                );
                if (!selected || selected.locked) return current;
                const next = current.filter(
                    (group) => group.id !== selected.id,
                );
                const index =
                    destination.afterId === null
                        ? 0
                        : next.findIndex(
                              (group) => group.id === destination.afterId,
                          ) + 1;
                next.splice(index, 0, selected);
                return next;
            }
            const selected = current
                .flatMap((group) => group.entries)
                .find((entry) => "entry-" + entry.id === itemId);
            if (!selected || selected.locked) return current;
            return current.map((group) => {
                const entries = group.entries.filter(
                    (entry) => entry.id !== selected.id,
                );
                if (group.id === destination.groupId) {
                    const index =
                        destination.afterId === null
                            ? 0
                            : entries.findIndex(
                                  (entry) => entry.id === destination.afterId,
                              ) + 1;
                    entries.splice(index, 0, selected);
                }
                return { ...group, entries };
            });
        });
        setLastMove(source.label + " moved.");
    }
    function note(entryId: string, value: string) {
        setGroups((current) =>
            current.map((group) => ({
                ...group,
                entries: group.entries.map((entry) =>
                    entry.id === entryId ? { ...entry, note: value } : entry,
                ),
            })),
        );
    }
    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <Field label="Read-only" htmlFor={readOnlyId} variant="toggle">
                    <Switch
                        id={readOnlyId}
                        name="read_only"
                        label="Read-only"
                        checked={readOnly}
                        onCheckedChange={setReadOnly}
                        size="sm"
                    />
                </Field>
                <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                        setGroups(example());
                        setLastMove("Example reset.");
                    }}
                    className="inline-flex items-center gap-1"
                >
                    Reset
                </Button>
            </div>
            <p className="text-sm text-muted">
                Move a planned group, or move an entry between groups. Recorded
                positions stay fixed.
            </p>
            <ReorderScope
                sources={sources}
                targets={targets}
                disabled={readOnly}
                onMove={({ itemId, targetId }) => move(itemId, targetId)}
            >
                <div className="relative grid gap-3">
                    {groups.map((group, index) => (
                        <ReorderItem key={group.id} id={"group-" + group.id}>
                            {({ ref, handle, active }) => (
                                <section
                                    ref={ref}
                                    aria-labelledby={"heading-" + group.id}
                                    data-group-id={group.id}
                                    data-moving={active || undefined}
                                    className={`relative min-w-0 rounded-box border border-box-border bg-surface ${active ? "opacity-40" : ""}`}
                                >
                                    <div className="absolute inset-x-0 top-0">
                                        <ReorderDropLine
                                            id={groupBoundaries[index]}
                                        />
                                    </div>
                                    <header className="flex items-center gap-2 px-3 py-2">
                                        {handle}
                                        <h2
                                            id={"heading-" + group.id}
                                            className="min-w-0 flex-1 text-sm font-medium"
                                        >
                                            {group.name}
                                        </h2>
                                        <span className="text-xs text-muted">
                                            {group.locked
                                                ? "Recorded"
                                                : group.entries.length +
                                                  " entries"}
                                        </span>
                                    </header>
                                    {group.entries.length ? (
                                        <Table>
                                            <caption className="sr-only">
                                                {group.name} entries
                                            </caption>
                                            <thead className="sr-only">
                                                <tr>
                                                    <th>Move</th>
                                                    <th>Entry</th>
                                                    <th>Note</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {group.entries.map(
                                                    (entry, position) => (
                                                        <ReorderItem
                                                            key={entry.id}
                                                            id={
                                                                "entry-" +
                                                                entry.id
                                                            }
                                                        >
                                                            {({
                                                                ref,
                                                                handle,
                                                                active,
                                                            }) => (
                                                                <tr
                                                                    ref={ref}
                                                                    data-entry-id={
                                                                        entry.id
                                                                    }
                                                                    data-moving={
                                                                        active ||
                                                                        undefined
                                                                    }
                                                                    className={
                                                                        active
                                                                            ? "relative opacity-40"
                                                                            : "relative"
                                                                    }
                                                                >
                                                                    <td className="w-8">
                                                                        {position ===
                                                                            0 && (
                                                                            <div className="absolute inset-x-0 top-0">
                                                                                <ReorderDropLine
                                                                                    id={
                                                                                        "entries-start-" +
                                                                                        group.id
                                                                                    }
                                                                                    align="start"
                                                                                />
                                                                            </div>
                                                                        )}
                                                                        {handle}
                                                                    </td>
                                                                    <td className="min-w-0 whitespace-normal text-sm">
                                                                        {
                                                                            entry.name
                                                                        }
                                                                    </td>
                                                                    <td className="w-36">
                                                                        <Input
                                                                            aria-label={
                                                                                "Note for " +
                                                                                entry.name
                                                                            }
                                                                            value={
                                                                                entry.note
                                                                            }
                                                                            onChange={(
                                                                                event,
                                                                            ) =>
                                                                                note(
                                                                                    entry.id,
                                                                                    event
                                                                                        .target
                                                                                        .value,
                                                                                )
                                                                            }
                                                                            readOnly={
                                                                                readOnly
                                                                            }
                                                                            className="min-w-0"
                                                                        />
                                                                        <div className="absolute inset-x-0 bottom-0">
                                                                            <ReorderDropLine
                                                                                id={
                                                                                    "entry-after-" +
                                                                                    entry.id
                                                                                }
                                                                                align="end"
                                                                            />
                                                                        </div>
                                                                    </td>
                                                                </tr>
                                                            )}
                                                        </ReorderItem>
                                                    ),
                                                )}
                                            </tbody>
                                        </Table>
                                    ) : (
                                        <div className="relative border-t border-box-border px-3 py-3">
                                            <div className="absolute inset-x-0 top-0">
                                                <ReorderDropLine
                                                    id={
                                                        "entries-start-" +
                                                        group.id
                                                    }
                                                    align="start"
                                                />
                                            </div>
                                            <p className="text-sm text-muted">
                                                No entries. Move a planned entry
                                                here.
                                            </p>
                                        </div>
                                    )}
                                </section>
                            )}
                        </ReorderItem>
                    ))}
                    <div className="absolute inset-x-0 bottom-0">
                        <ReorderDropLine id="groups-end" />
                    </div>
                </div>
            </ReorderScope>
            <p className="text-sm text-muted" aria-live="polite">
                {lastMove}
            </p>
        </div>
    );
}
