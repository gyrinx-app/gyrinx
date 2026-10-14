import { useId, useState } from "react";
import { Button, FieldErrors, RadioOption } from "../../ui";

export type TerritoryBoonChoicesProps = {
    groups: {
        key: string;
        label: string;
        selected: string;
        options: {
            value: string;
            label: string;
            description: string;
            disabled: boolean;
        }[];
    }[];
    effects: { name: string; text: string }[];
    saveUrl: string;
    csrfToken: string;
    snapshot: string;
};

export function TerritoryBoonChoices(
    props: TerritoryBoonChoicesProps & {
        onSave: (values: Record<string, string>) => Promise<void>;
    },
) {
    const id = useId();
    const original = Object.fromEntries(
        props.groups.map((group) => [group.key, group.selected]),
    );
    const [selected, setSelected] = useState(original);
    const [pending, setPending] = useState(false);
    const [error, setError] = useState("");
    const dirty = props.groups.some(
        (group) => selected[group.key] !== original[group.key],
    );
    return (
        <form
            onSubmit={async (event) => {
                event.preventDefault();
                if (!dirty || pending) return;
                setPending(true);
                setError("");
                try {
                    await props.onSave(
                        Object.fromEntries(
                            props.groups
                                .filter(
                                    (group) =>
                                        selected[group.key] !==
                                        original[group.key],
                                )
                                .map((group) => [
                                    group.key,
                                    selected[group.key],
                                ]),
                        ),
                    );
                } catch (failure) {
                    setError(
                        failure instanceof Error
                            ? failure.message
                            : "Could not save boons. Try again.",
                    );
                    setPending(false);
                }
            }}
        >
            <div className="divide-y divide-box-border">
                {props.groups.map((group, index) => (
                    <div
                        key={group.key}
                        className={
                            props.groups.length > 1
                                ? "grid min-w-0 gap-2 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] sm:gap-4"
                                : "min-w-0 py-3"
                        }
                    >
                        <div
                            id={`${id}-group-${index}`}
                            className={
                                props.groups.length > 1
                                    ? "pt-2 text-sm font-medium"
                                    : "sr-only"
                            }
                        >
                            {group.label}
                        </div>
                        <fieldset
                            aria-labelledby={`${id}-group-${index}`}
                            disabled={pending}
                            className="min-w-0"
                        >
                            {group.options.map((option) => (
                                <RadioOption
                                    key={option.value}
                                    name={`choice_${group.key}`}
                                    value={option.value}
                                    label={option.label}
                                    description={option.description}
                                    checked={
                                        selected[group.key] === option.value
                                    }
                                    disabled={option.disabled}
                                    onChange={() => {
                                        setError("");
                                        setSelected((previous) => ({
                                            ...previous,
                                            [group.key]: option.value,
                                        }));
                                    }}
                                />
                            ))}
                        </fieldset>
                    </div>
                ))}
            </div>
            {props.effects.length > 0 && (
                <div className="space-y-2 border-t border-box-border pt-3">
                    {props.effects.map((effect, index) => (
                        <p key={`${index}-${effect.name}`} className="text-sm">
                            <span className="text-muted">{effect.name}</span>{" "}
                            {effect.text}
                        </p>
                    ))}
                </div>
            )}
            {error && (
                <div role="alert" className="mt-3">
                    <FieldErrors errors={[error]} />
                </div>
            )}
            <div className="mt-4 flex justify-end">
                <Button
                    type="submit"
                    variant="success"
                    size="sm"
                    disabled={!dirty || pending}
                >
                    {pending ? "Saving…" : "Save"}
                </Button>
            </div>
        </form>
    );
}
