import { useState } from "react";

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
    fixed: { setKey: string; price: number }[] = [],
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
        // A default set can be offered in more than one group, but is held once.
        price: [
            ...new Map(
                [...fixed, ...picked].map((option) => [
                    option.setKey,
                    option.price,
                ]),
            ).values(),
        ].reduce((sum, price) => sum + price, 0),
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
}: {
    groups: PickGroup[];
    selected: Record<string, string[]>;
    onPick: (group: PickGroup, value: string, checked: boolean) => void;
}) {
    return groups.map((group, index) => (
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
                        type={group.choose === "any" ? "checkbox" : "radio"}
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
                            onPick(group, option.value, event.target.checked)
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
    ));
}
