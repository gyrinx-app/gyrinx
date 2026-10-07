import { useLayoutEffect, useRef, useState } from "react";
import { CheckboxCard } from "../../ui";

export type PrintWeapon = {
    id: string;
    label: string;
    slots: number;
    slotsLabel: string;
    rating: number;
    ticked: boolean;
};

export type PrintModel = {
    id: string;
    name: string;
    profileName: string;
    rating: number;
    baseRating: number;
    ticked: boolean;
    hasWeapons: boolean;
    weapons: PrintWeapon[];
};

export type PrintPickerProps = {
    /** The hidden input's name that tells the server the boxes were sent; empty for none. */
    marker: string;
    slotBudget: number;
    models: PrintModel[];
    /** Ticks the server-drawn boxes showed at mount, by id; they win over `ticked`. */
    shown?: {
        fighters: Record<string, boolean>;
        weapons: Record<string, boolean>;
    };
    /** The server-drawn box that had focus at mount, to focus again. */
    focus?: { name: string; value: string } | null;
};

/**
 * The print setup's model and weapon boxes, inside the page's own form.
 *
 * The checkboxes post `fighters` and `weapons` themselves. A weapon box is
 * disabled while its model is unticked, so it stays out of the submission
 * but keeps its tick for when the model comes back. The slot counts and
 * the crew total are a preview; the print reckons its own. The hidden
 * marker tells the server the boxes were part of the submission, so a
 * failed island cannot save an empty setup.
 */
export function PrintPicker({
    marker,
    slotBudget,
    models,
    shown,
    focus = null,
}: PrintPickerProps) {
    const root = useRef<HTMLDivElement>(null);
    const [pickedModels, setPickedModels] = useState(
        () =>
            new Set(
                models
                    .filter(
                        (model) => shown?.fighters[model.id] ?? model.ticked,
                    )
                    .map((model) => model.id),
            ),
    );
    const [pickedWeapons, setPickedWeapons] = useState(
        () =>
            new Set(
                models.flatMap((model) =>
                    model.weapons
                        .filter(
                            (weapon) =>
                                shown?.weapons[weapon.id] ?? weapon.ticked,
                        )
                        .map((weapon) => weapon.id),
                ),
            ),
    );

    useLayoutEffect(() => {
        if (!focus) return;
        const box = Array.from(
            root.current?.querySelectorAll<HTMLInputElement>(
                `input[name="${focus.name}"]`,
            ) ?? [],
        ).find((input) => input.value === focus.value);
        box?.focus();
    }, [focus]);

    function toggle(
        set: (update: (previous: Set<string>) => Set<string>) => void,
        id: string,
        on: boolean,
    ) {
        set((previous) => {
            const next = new Set(previous);
            if (on) next.add(id);
            else next.delete(id);
            return next;
        });
    }

    const total = models
        .filter((model) => pickedModels.has(model.id))
        .reduce(
            (sum, model) =>
                sum +
                model.baseRating +
                model.weapons
                    .filter((weapon) => pickedWeapons.has(weapon.id))
                    .reduce((weapons, weapon) => weapons + weapon.rating, 0),
            0,
        );

    return (
        <div ref={root} className="space-y-4">
            {marker && <input type="hidden" name={marker} value="1" />}
            <div className="grid auto-rows-min grid-cols-1 gap-4 md:grid-cols-2">
                {models.map((model) => {
                    const picked = pickedModels.has(model.id);
                    const slots = model.weapons
                        .filter((weapon) => pickedWeapons.has(weapon.id))
                        .reduce((used, weapon) => used + weapon.slots, 0);
                    return (
                        <CheckboxCard
                            key={model.id}
                            className="h-full"
                            name="fighters"
                            value={model.id}
                            label={model.name}
                            description={model.profileName}
                            checked={picked}
                            onCheckedChange={(on) =>
                                toggle(setPickedModels, model.id, on)
                            }
                            meta={
                                <>
                                    {model.hasWeapons && (
                                        <span
                                            className={`shrink-0 text-xs tabular-nums ${
                                                slots > slotBudget
                                                    ? "font-medium text-amber-600 dark:text-amber-400"
                                                    : "text-muted"
                                            }`}
                                            title={`Weapon slots used (${slotBudget} per card)`}
                                        >
                                            {slots}/{slotBudget} slots
                                        </span>
                                    )}
                                    <span className="shrink-0 text-sm tabular-nums text-muted">
                                        {model.rating}¢
                                    </span>
                                </>
                            }
                        >
                            {model.weapons.length > 0 &&
                                model.weapons.map((weapon) => (
                                    <label
                                        key={weapon.id}
                                        className="flex min-h-9 cursor-pointer items-center gap-2.5 rounded-control px-1 hover:bg-ink-500/5"
                                    >
                                        <input
                                            type="checkbox"
                                            name="weapons"
                                            value={weapon.id}
                                            checked={pickedWeapons.has(
                                                weapon.id,
                                            )}
                                            disabled={!picked}
                                            onChange={(event) =>
                                                toggle(
                                                    setPickedWeapons,
                                                    weapon.id,
                                                    event.target.checked,
                                                )
                                            }
                                            className="size-4 shrink-0 accent-[var(--color-accent)] focus-ring"
                                        />
                                        <span className="min-w-0 flex-1 truncate text-sm text-ink-900 dark:text-ink-100">
                                            {weapon.label}
                                        </span>
                                        {weapon.slotsLabel && (
                                            <span className="shrink-0 text-xs text-muted">
                                                {weapon.slotsLabel}
                                            </span>
                                        )}
                                        <span className="shrink-0 text-xs tabular-nums text-muted">
                                            {weapon.rating}¢
                                        </span>
                                    </label>
                                ))}
                        </CheckboxCard>
                    );
                })}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-x-6 gap-y-1 text-sm">
                <span className="text-muted" aria-live="polite">
                    Crew total{" "}
                    <span className="ml-1 font-medium tabular-nums text-ink-900 dark:text-ink-100">
                        {total}¢
                    </span>
                </span>
            </div>
        </div>
    );
}
