import { useRef } from "react";
import { Button, Field, Input, NativeSelect } from "../../ui";
import type { Phase, Step } from "./types";

export function PlanSteps({
    value,
    onChange,
    phases,
    disabled,
}: {
    value: string;
    onChange: (value: string) => void;
    phases: Phase[];
    disabled: boolean;
}) {
    let steps: Step[] = [];
    try {
        const parsed: unknown = JSON.parse(value);
        if (
            Array.isArray(parsed) &&
            parsed.every(
                (step: unknown) =>
                    typeof step === "object" &&
                    step !== null &&
                    "id" in step &&
                    typeof step.id === "string" &&
                    "phase_id" in step &&
                    typeof step.phase_id === "string" &&
                    "count" in step &&
                    typeof step.count === "number",
            )
        )
            steps = parsed;
    } catch {
        /* Keep the original hidden payload for server validation and retries. */
    }
    const dragging = useRef<number | null>(null);
    const save = (next: Step[]) => onChange(JSON.stringify(next));
    function move(from: number, to: number) {
        if (disabled || to < 0 || to >= steps.length || from === to) return;
        const next = [...steps];
        const [step] = next.splice(from, 1);
        next.splice(to, 0, step);
        save(next);
    }
    return (
        <div className="space-y-3">
            <p className="text-sm text-muted">
                Drag steps to reorder them, or use Earlier and Later.
            </p>
            <ol className="space-y-3">
                {steps.map((step, index) => (
                    <li
                        key={step.id}
                        draggable={!disabled}
                        onDragStart={(event) => {
                            dragging.current = index;
                            event.dataTransfer.setData(
                                "text/plain",
                                String(index),
                            );
                        }}
                        onDragOver={(event) => {
                            if (!disabled) event.preventDefault();
                        }}
                        onDrop={(event) => {
                            event.preventDefault();
                            if (dragging.current !== null)
                                move(dragging.current, index);
                            dragging.current = null;
                        }}
                        className="rounded-control border border-box-border p-3 space-y-3"
                    >
                        <div className="grid grid-cols-[minmax(0,1fr)_5rem] gap-3">
                            <Field
                                label={`Step ${index + 1} phase`}
                                htmlFor={`step-${step.id}-phase`}
                            >
                                <NativeSelect
                                    value={step.phase_id}
                                    onChange={(event) =>
                                        save(
                                            steps.map((item, i) =>
                                                i === index
                                                    ? {
                                                          ...item,
                                                          phase_id:
                                                              event.target
                                                                  .value,
                                                      }
                                                    : item,
                                            ),
                                        )
                                    }
                                >
                                    {phases.map((phase) => (
                                        <option key={phase.id} value={phase.id}>
                                            {phase.name}
                                        </option>
                                    ))}
                                </NativeSelect>
                            </Field>
                            <Field
                                label="Cycles"
                                htmlFor={`step-${step.id}-count`}
                            >
                                <Input
                                    type="number"
                                    min="1"
                                    step="1"
                                    required
                                    value={step.count}
                                    onChange={(event) =>
                                        save(
                                            steps.map((item, i) =>
                                                i === index
                                                    ? {
                                                          ...item,
                                                          count: Number(
                                                              event.target
                                                                  .value,
                                                          ),
                                                      }
                                                    : item,
                                            ),
                                        )
                                    }
                                />
                            </Field>
                        </div>
                        <div className="flex flex-wrap gap-2">
                            <Button
                                size="xs"
                                disabled={disabled || index === 0}
                                aria-label={`Move step ${index + 1} earlier`}
                                onClick={() => move(index, index - 1)}
                            >
                                Earlier
                            </Button>
                            <Button
                                size="xs"
                                disabled={
                                    disabled || index === steps.length - 1
                                }
                                aria-label={`Move step ${index + 1} later`}
                                onClick={() => move(index, index + 1)}
                            >
                                Later
                            </Button>
                            <Button
                                size="xs"
                                variant="ghost"
                                aria-label={`Remove step ${index + 1}`}
                                onClick={() =>
                                    save(steps.filter((_, i) => i !== index))
                                }
                            >
                                Remove
                            </Button>
                        </div>
                    </li>
                ))}
            </ol>
            <Button
                disabled={disabled || !phases.length}
                onClick={() =>
                    save([
                        ...steps,
                        {
                            id: crypto
                                .randomUUID()
                                .replaceAll("-", "")
                                .slice(0, 26),
                            phase_id: phases[0].id,
                            count: 1,
                        },
                    ])
                }
            >
                Add step
            </Button>
        </div>
    );
}
