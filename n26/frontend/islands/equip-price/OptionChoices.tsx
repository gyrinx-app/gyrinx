import { useLayoutEffect, useRef, useState } from "react";

export type FocusedChoice = { field: string; value: string };
export type ResolutionGroup = {
    choose: "one" | "one-or-none" | "any";
    options: { setKey: string; price: number }[];
};

/** Resolve named sets in the server's group order, including hidden defaults. */
export function resolveOptions(groups: ResolutionGroup[], named: string[]) {
    const remaining = [...named];
    const resolved: ResolutionGroup["options"] = [];
    for (const group of groups) {
        let taken = group.options.filter((option) =>
            remaining.includes(option.setKey),
        );
        for (const option of taken) {
            const index = remaining.indexOf(option.setKey);
            if (index < 0) return null;
            remaining.splice(index, 1);
        }
        if (group.choose !== "any" && taken.length > 1) return null;
        if (taken.length === 0 && group.choose === "one")
            taken = group.options.slice(0, 1);
        resolved.push(...taken);
    }
    return remaining.length ? null : resolved;
}

export type PickGroup = {
    field: string;
    choose: "one" | "one-or-none" | "any";
    nothingTaken: boolean;
    options: {
        name: string;
        value: string;
        surcharge: number;
        surchargeLabel: string;
        price: number;
        setKey: string;
        checked: boolean;
    }[];
};

export function useChoices(
    groups: PickGroup[],
    initial?: Record<string, string[]>,
) {
    const [selected, setSelected] = useState<Record<string, string[]>>(() =>
        Object.fromEntries(
            groups.map((group) => {
                const values =
                    initial?.[group.field] ??
                    group.options
                        .filter((option) => option.checked)
                        .map((option) => option.value);
                return [
                    group.field,
                    group.choose === "one" && values.length === 0
                        ? group.options
                              .slice(0, 1)
                              .map((option) => option.value)
                        : values,
                ];
            }),
        ),
    );
    const picked = groups.flatMap((group) =>
        group.options.filter((option) =>
            selected[group.field]?.includes(option.value),
        ),
    );
    return {
        selected,
        surcharge: picked.reduce((sum, option) => sum + option.surcharge, 0),
        picked,
        onPick(group: PickGroup, value: string, checked: boolean) {
            setSelected((previous) => ({
                ...previous,
                [group.field]:
                    group.choose === "any"
                        ? checked
                            ? [...previous[group.field], value]
                            : previous[group.field].filter(
                                  (entry) => entry !== value,
                              )
                        : value === ""
                          ? []
                          : [value],
            }));
        },
    };
}

export function OptionChoices({
    groups,
    selected,
    onPick,
    focusedChoice,
}: {
    groups: PickGroup[];
    selected: Record<string, string[]>;
    onPick: (group: PickGroup, value: string, checked: boolean) => void;
    focusedChoice?: FocusedChoice;
}) {
    const root = useRef<HTMLDivElement>(null);
    useLayoutEffect(() => {
        if (!focusedChoice) return;
        const input = Array.from(
            root.current?.querySelectorAll<HTMLInputElement>("input") ?? [],
        ).find(
            (input) =>
                input.name === focusedChoice.field &&
                input.value === focusedChoice.value,
        );
        input?.focus();
    }, [focusedChoice]);
    return (
        <div ref={root}>
            {groups.map((group, index) => (
                <fieldset key={group.field} className="min-w-0">
                    <legend
                        className={
                            index === 0
                                ? "sr-only"
                                : "mt-1 flex min-h-8 items-center gap-2 pt-1 text-xs font-semibold uppercase tracking-wide text-muted"
                        }
                    >
                        {group.choose === "one"
                            ? "Choose one"
                            : group.choose === "any"
                              ? "Choose any"
                              : "Choose one, or none"}
                    </legend>
                    {[
                        ...group.options,
                        ...(group.choose === "one-or-none"
                            ? [{ name: "None", value: "", surchargeLabel: "" }]
                            : []),
                    ].map((option) => (
                        <label
                            key={option.value}
                            className={`flex min-h-9 cursor-pointer items-center gap-2 rounded-control py-0.5 hover:bg-ink-500/5 ${index > 0 ? "n26-cp-substep" : ""}`}
                        >
                            <input
                                type={
                                    group.choose === "any"
                                        ? "checkbox"
                                        : "radio"
                                }
                                name={group.field}
                                value={option.value}
                                checked={
                                    option.value === ""
                                        ? selected[group.field]?.length === 0
                                        : (selected[group.field]?.includes(
                                              option.value,
                                          ) ?? false)
                                }
                                onChange={(event) =>
                                    onPick(
                                        group,
                                        option.value,
                                        event.target.checked,
                                    )
                                }
                                className="size-4 shrink-0 accent-[var(--color-accent)] focus-ring"
                            />
                            <span className="min-w-0 text-sm text-ink-900 dark:text-ink-100 sm:truncate">
                                {option.name}
                            </span>{" "}
                            {option.surchargeLabel && (
                                <span className="shrink-0 text-xs text-muted">
                                    {option.surchargeLabel}
                                </span>
                            )}
                        </label>
                    ))}
                </fieldset>
            ))}
        </div>
    );
}
