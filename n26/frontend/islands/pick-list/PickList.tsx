import { useState } from "react";
import {
    Button,
    PickBox,
    PickLegend,
    QuickSwitcher,
    type PickOption,
} from "../../ui";

type PickGroup = { name: string; caption: string; options: PickOption[] };

export type PickListProps = {
    /** The checkboxes' field name. */
    name: string;
    groups: PickGroup[];
    /** Options not on the list, offered by the switcher and listed once ticked. */
    addable: PickOption[];
    addLabel: string;
    placeholder: string;
    grouped: boolean;
    /** Heads the ticked addable options when the list is grouped. */
    addedLabel: string;
    /** The submit button's words; empty draws no buttons. */
    save: string;
    /** The form a Reset button submits; empty draws no Reset. */
    resetForm: string;
};

function initiallyPicked(groups: PickGroup[], addable: PickOption[]) {
    return new Set(
        [...groups.flatMap((group) => group.options), ...addable]
            .filter((option) => option.picked)
            .map((option) => option.key),
    );
}

/**
 * A ticked list with a switcher for what is not on it yet. Only the boxes
 * post: the switcher ticks a box, and adds no input of its own.
 */
export function PickList({
    name,
    groups,
    addable,
    addLabel,
    placeholder,
    grouped,
    addedLabel,
    save,
    resetForm,
}: PickListProps) {
    const [opened] = useState(() => initiallyPicked(groups, addable));
    const [picked, setPicked] = useState(() => new Set(opened));
    const dirty =
        picked.size !== opened.size ||
        [...picked].some((key) => !opened.has(key));

    function tick(key: string, on: boolean) {
        setPicked((previous) => {
            const next = new Set(previous);
            if (on) next.add(key);
            else next.delete(key);
            return next;
        });
    }

    const box = (option: PickOption) => (
        <PickBox
            key={option.key}
            option={option}
            name={name}
            checked={picked.has(option.key)}
            onChange={(on) => tick(option.key, on)}
        />
    );
    const added = addable.filter((option) => picked.has(option.key));
    const offered = addable
        .filter((option) => !picked.has(option.key))
        .map((option) => ({ label: option.name, value: option.key }));

    return (
        <div>
            <div className={grouped ? "space-y-4" : "flex flex-col"}>
                {groups.map((group, index) =>
                    grouped ? (
                        <fieldset key={`${group.name}-${index}`}>
                            <PickLegend
                                name={group.name}
                                caption={group.caption}
                            />
                            <div className="flex flex-col">
                                {group.options.map(box)}
                            </div>
                        </fieldset>
                    ) : (
                        group.options.map(box)
                    ),
                )}
                {grouped && addedLabel
                    ? added.length > 0 && (
                          <fieldset>
                              <PickLegend name={addedLabel} caption="" />
                              <div className="flex flex-col">
                                  {added.map(box)}
                              </div>
                          </fieldset>
                      )
                    : added.map(box)}
            </div>
            {addable.length > 0 && (
                <div className="mt-2">
                    <QuickSwitcher
                        heading={addLabel}
                        menuLabel={addLabel}
                        triggerWords={addLabel}
                        placeholder={placeholder}
                        minWidth="20rem"
                        items={offered}
                        onChoose={(key) => tick(key, true)}
                    />
                </div>
            )}
            {save && (
                <div className="mt-3 flex items-center justify-end gap-2">
                    {resetForm && (
                        <Button
                            type="submit"
                            form={resetForm}
                            variant="subtle"
                            size="sm"
                        >
                            Reset
                        </Button>
                    )}
                    <Button
                        type="submit"
                        variant="success"
                        size="sm"
                        disabled={!dirty}
                    >
                        {save}
                    </Button>
                </div>
            )}
        </div>
    );
}
