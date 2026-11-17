import { Button, Icon, Input, NativeSelect, Table } from "../../ui";
import {
    ReorderScope,
    ReorderItem,
    ReorderDropLine,
    type ReorderSource,
} from "../../ui/reorder";
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
    const identitiesValid =
        steps.every((step) => !!step.id.trim()) &&
        new Set(steps.map((step) => step.id)).size === steps.length;
    const targets = [
        ...steps.map((step, index) => ({
            id: "before-" + (identitiesValid ? step.id : index),
            label: "Before step " + (index + 1),
        })),
        { id: "steps-end", label: "After the last step" },
    ];
    const sources = identitiesValid
        ? steps.map((step, index) => ({
              id: step.id,
              label: "step " + (index + 1),
              origin: targets[index].id,
              targets: targets
                  .filter(
                      (_, boundary) =>
                          boundary !== index && boundary !== index + 1,
                  )
                  .map((target) => target.id),
          }))
        : [];
    function moveToBoundary(itemId: string, targetId: string) {
        if (disabled || !identitiesValid) return;
        const source = sources.find((item) => item.id === itemId);
        if (!source?.targets.includes(targetId)) return;
        const boundary = targets.findIndex((target) => target.id === targetId);
        const afterId = boundary > 0 ? steps[boundary - 1].id : null;
        const selected = steps.find((step) => step.id === itemId);
        if (!selected) return;
        const next = steps.filter((step) => step.id !== itemId);
        const destination =
            afterId === null
                ? 0
                : next.findIndex((step) => step.id === afterId) + 1;
        next.splice(destination, 0, selected);
        save(next);
    }
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
                Move steps with the handles or arrow buttons.
            </p>
            <ReorderScope
                sources={sources}
                targets={targets}
                disabled={disabled}
                onMove={({ itemId, targetId }) =>
                    moveToBoundary(itemId, targetId)
                }
            >
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
                            <ReorderItem
                                key={identitiesValid ? step.id : index}
                                id={
                                    identitiesValid
                                        ? step.id
                                        : "invalid-step-" + index
                                }
                            >
                                {({ ref, handle, active }) => (
                                    <tr
                                        ref={ref}
                                        data-step-id={step.id}
                                        data-moving={active || undefined}
                                        className="relative max-sm:grid max-sm:grid-cols-[4rem_minmax(0,1fr)] max-sm:gap-x-2"
                                    >
                                        <td className="w-20 max-sm:block max-sm:w-auto">
                                            <div className="absolute inset-x-0 top-0">
                                                <ReorderDropLine
                                                    id={targets[index].id}
                                                    align="start"
                                                />
                                            </div>
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
                                                            steps.map(
                                                                (item, i) =>
                                                                    i === index
                                                                        ? {
                                                                              ...item,
                                                                              count: Number(
                                                                                  event
                                                                                      .target
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
                                                                          event
                                                                              .target
                                                                              .value,
                                                                  }
                                                                : item,
                                                        ),
                                                    )
                                                }
                                            >
                                                {phases.map((phase) => (
                                                    <option
                                                        key={phase.id}
                                                        value={phase.id}
                                                    >
                                                        {phase.name}
                                                    </option>
                                                ))}
                                            </NativeSelect>
                                        </td>
                                        <td className="w-px whitespace-nowrap max-sm:col-span-2 max-sm:block max-sm:w-auto">
                                            <div className="flex items-center justify-end gap-0.5">
                                                {handle}
                                                <Button
                                                    size="xs"
                                                    variant="ghost"
                                                    disabled={
                                                        disabled || index === 0
                                                    }
                                                    aria-label={`Move step ${index + 1} earlier`}
                                                    title="Move earlier"
                                                    onClick={() =>
                                                        move(index, index - 1)
                                                    }
                                                >
                                                    <Icon name="arrow-up" />
                                                </Button>
                                                <Button
                                                    size="xs"
                                                    variant="ghost"
                                                    disabled={
                                                        disabled ||
                                                        index ===
                                                            steps.length - 1
                                                    }
                                                    aria-label={`Move step ${index + 1} later`}
                                                    title="Move later"
                                                    onClick={() =>
                                                        move(index, index + 1)
                                                    }
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
                                                                (_, i) =>
                                                                    i !== index,
                                                            ),
                                                        )
                                                    }
                                                >
                                                    <Icon name="trash-2" />
                                                </Button>
                                            </div>
                                            {index === steps.length - 1 && (
                                                <div className="absolute inset-x-0 bottom-0">
                                                    <ReorderDropLine
                                                        id="steps-end"
                                                        align="end"
                                                    />
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                )}
                            </ReorderItem>
                        ))}
                    </tbody>
                </Table>
            </ReorderScope>
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
                    {steps.length ? (
                        <>
                            Ends after Cycle{" "}
                            {startsAfterOrder +
                                steps.reduce(
                                    (total, step) => total + step.count,
                                    0,
                                )}
                            .
                        </>
                    ) : (
                        "No additional cycles."
                    )}
                </p>
            )}
        </div>
    );
}
