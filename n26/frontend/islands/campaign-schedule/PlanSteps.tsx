import { useRef } from "react";
import { Button, Icon, Input, NativeSelect, Table } from "../../ui";
import type { Phase, Step } from "./types";

export function PlanSteps({
    value,
    onChange,
    phases,
    disabled,
    startsAfterOrder,
}: {
    value: string;
    onChange: (value: string) => void;
    phases: Phase[];
    disabled: boolean;
    startsAfterOrder?: number;
}) {
    let steps: Step[] = [];
    let valid = false;
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
        ) {
            steps = parsed;
            valid = parsed.every(
                (step) => Number.isInteger(step.count) && step.count > 0,
            );
        }
    } catch {
        /* Keep the original hidden payload for server validation and exact retries. */
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
        <div className="space-y-2">
            <p className="text-xs text-muted">
                Drag steps, or use the arrow buttons to reorder them.
            </p>
            <Table className="max-sm:block">
                <caption className="sr-only">Future phase steps</caption>
                <thead className="max-sm:block">
                    <tr className="max-sm:grid max-sm:grid-cols-[4rem_minmax(0,1fr)] max-sm:gap-x-2">
                        <th scope="col">Cycles</th>
                        <th scope="col">Phase</th>
                        <th scope="col" className="max-sm:sr-only">
                            <span className="sr-only">Step actions</span>
                        </th>
                    </tr>
                </thead>
                <tbody className="max-sm:block">
                    {steps.map((step, index) => (
                        <tr
                            key={step.id}
                            className="max-sm:grid max-sm:grid-cols-[4rem_minmax(0,1fr)] max-sm:gap-x-2"
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
                        >
                            <td className="w-20 max-sm:block max-sm:w-auto">
                                <div className="w-14">
                                    <Input
                                        type="number"
                                        min="1"
                                        step="1"
                                        required
                                        disabled={disabled}
                                        value={step.count}
                                        aria-label={`Step ${index + 1} cycles`}
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
                                </div>
                            </td>
                            <td className="w-full min-w-0 max-sm:block">
                                <NativeSelect
                                    controlSize="sm"
                                    className="min-w-0"
                                    disabled={disabled}
                                    value={step.phase_id}
                                    aria-label={`Step ${index + 1} phase`}
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
                            </td>
                            <td className="w-px whitespace-nowrap max-sm:col-span-2 max-sm:block max-sm:w-auto">
                                <div className="flex items-center justify-end gap-0.5">
                                    <Button
                                        size="xs"
                                        variant="ghost"
                                        disabled={disabled || index === 0}
                                        aria-label={`Move step ${index + 1} earlier`}
                                        title="Move earlier"
                                        onClick={() => move(index, index - 1)}
                                    >
                                        <Icon name="arrow-up" />
                                    </Button>
                                    <Button
                                        size="xs"
                                        variant="ghost"
                                        disabled={
                                            disabled ||
                                            index === steps.length - 1
                                        }
                                        aria-label={`Move step ${index + 1} later`}
                                        title="Move later"
                                        onClick={() => move(index, index + 1)}
                                    >
                                        <Icon name="arrow-down" />
                                    </Button>
                                    <Button
                                        size="xs"
                                        variant="ghost"
                                        disabled={disabled}
                                        aria-label={`Remove step ${index + 1}`}
                                        title="Remove step"
                                        onClick={() =>
                                            save(
                                                steps.filter(
                                                    (_, i) => i !== index,
                                                ),
                                            )
                                        }
                                    >
                                        <Icon name="trash-2" />
                                    </Button>
                                </div>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </Table>
            <Button
                size="sm"
                variant="ghost"
                className="inline-flex items-center gap-2 whitespace-nowrap"
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
                <Icon name="plus" /> Add step
            </Button>
            {startsAfterOrder !== undefined && valid && (
                <p className="text-sm text-muted" aria-live="polite">
                    Ends after Cycle{" "}
                    {startsAfterOrder +
                        steps.reduce((total, step) => total + step.count, 0)}
                    .
                </p>
            )}
        </div>
    );
}
