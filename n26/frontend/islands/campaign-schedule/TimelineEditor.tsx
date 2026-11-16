import { useId } from "react";
import {
    Field,
    FieldDescription,
    FieldErrors,
    Input,
    NativeSelect,
    Toggle,
} from "../../ui";
import type { Editor } from "./types";

type TimelineOccurrence = {
    id: string;
    number: number;
    name: string;
    cycles: Array<{ id: string; name: string; order: number }>;
};

export const timelineFields: Record<string, string[]> = {
    "plan-cycles": ["pattern_count"],
    "add-cycle": [
        "after_cycle_id",
        "custom_name",
        "starts_on",
        "ends_on",
        "description",
        "effects",
    ],
    "move-cycle": ["occurrence_id", "after_cycle_id"],
    "duplicate-cycle": ["occurrence_id", "after_cycle_id", "clear_dates"],
    "move-phase": ["after_occurrence_id"],
    "duplicate-phase": ["name", "clear_dates"],
};

export function TimelineEditor({
    editor,
    values,
    errors,
    onChange,
}: {
    editor: Editor;
    values: Record<string, string>;
    errors: Record<string, string[]>;
    onChange: (values: Record<string, string>) => void;
}) {
    const copyDatesHelp = useId();
    if (!(editor.kind in timelineFields)) return null;
    if (editor.kind === "plan-cycles")
        return (
            <Field
                label="Cycles to add"
                htmlFor="cycle-pattern_count"
                errors={errors.pattern_count}
                description="You can edit these cycles after you add them."
            >
                <Input
                    name="pattern_count"
                    type="number"
                    min="1"
                    max="1000"
                    step="1"
                    required
                    value={values.pattern_count ?? ""}
                    onChange={(event) =>
                        onChange({
                            ...values,
                            pattern_count: event.target.value,
                        })
                    }
                />
            </Field>
        );
    const occurrences = (editor.context.timelineOccurrences ??
        []) as TimelineOccurrence[];
    const selected = editor.context.selectedCycle as
        | { id: string; name: string; order: number; occurrenceId: string }
        | undefined;
    const occurrence = occurrences.find(
        (item) => item.id === values.occurrence_id,
    );
    const label = (item: TimelineOccurrence) =>
        `${String(item.number).padStart(2, "0")} ${item.name}`;
    if (editor.kind === "move-phase")
        return (
            <Field
                label="Move phase after"
                htmlFor="cycle-after_occurrence_id"
                errors={errors.after_occurrence_id}
            >
                <NativeSelect
                    name="after_occurrence_id"
                    value={values.after_occurrence_id ?? ""}
                    onChange={(event) =>
                        onChange({
                            ...values,
                            after_occurrence_id: event.target.value,
                        })
                    }
                >
                    <option value="">Start of timeline</option>
                    {occurrences
                        .filter((item) => item.id !== values.occurrence_id)
                        .map((item) => (
                            <option key={item.id} value={item.id}>
                                {label(item)}
                            </option>
                        ))}
                </NativeSelect>
            </Field>
        );
    return (
        <div className="space-y-3">
            {editor.kind === "duplicate-phase" ? null : editor.kind ===
              "add-cycle" ? (
                occurrence && (
                    <p className="text-sm text-muted">
                        Phase {label(occurrence)}
                    </p>
                )
            ) : (
                <Field
                    label="Phase block"
                    htmlFor="cycle-occurrence_id"
                    errors={errors.occurrence_id}
                >
                    <NativeSelect
                        name="occurrence_id"
                        value={values.occurrence_id ?? ""}
                        required
                        onChange={(event) =>
                            onChange({
                                ...values,
                                occurrence_id: event.target.value,
                                after_cycle_id: "",
                            })
                        }
                    >
                        <option value="">Choose a phase block</option>
                        {occurrences.map((item) => (
                            <option key={item.id} value={item.id}>
                                {label(item)}
                            </option>
                        ))}
                    </NativeSelect>
                </Field>
            )}
            {editor.kind !== "duplicate-phase" && (
                <Field
                    label={
                        editor.kind === "move-cycle"
                            ? "Move cycle after"
                            : "Add cycle after"
                    }
                    htmlFor="cycle-after_cycle_id"
                    errors={errors.after_cycle_id}
                >
                    <NativeSelect
                        name="after_cycle_id"
                        value={values.after_cycle_id ?? ""}
                        onChange={(event) =>
                            onChange({
                                ...values,
                                after_cycle_id: event.target.value,
                            })
                        }
                    >
                        <option value="">Start of phase</option>
                        {(occurrence?.cycles ?? [])
                            .filter(
                                (cycle) =>
                                    editor.kind !== "move-cycle" ||
                                    cycle.id !==
                                        (values.cycle_id ?? selected?.id),
                            )
                            .map((cycle) => (
                                <option key={cycle.id} value={cycle.id}>
                                    {String(cycle.order).padStart(2, "0")}{" "}
                                    {cycle.name}
                                </option>
                            ))}
                    </NativeSelect>
                </Field>
            )}
            {["duplicate-cycle", "duplicate-phase"].includes(editor.kind) && (
                <div
                    className="space-y-1"
                    role="group"
                    aria-label="Copied dates"
                    aria-describedby={copyDatesHelp}
                >
                    <input
                        type="hidden"
                        name="clear_dates"
                        value={values.clear_dates ?? "True"}
                    />
                    <Toggle
                        label="Leave copied dates blank"
                        checked={
                            !["", "False", "false"].includes(values.clear_dates)
                        }
                        onCheckedChange={(checked) =>
                            onChange({
                                ...values,
                                clear_dates: checked ? "on" : "",
                            })
                        }
                    />
                    <FieldDescription id={copyDatesHelp}>
                        Leave this off to copy the dates too.
                    </FieldDescription>
                    <FieldErrors errors={errors.clear_dates ?? []} />
                </div>
            )}
        </div>
    );
}
