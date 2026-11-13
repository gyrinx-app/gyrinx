import { useState } from "react";
import { Button, Field, Icon, Input, Table, Textarea } from "../../ui";
import { RewardSettings } from "./RewardSettings";
import { PlanSteps } from "./PlanSteps";
import type { Phase, SetupDefinition } from "./types";

export function setupDraft(value: string): SetupDefinition | null {
    try {
        const data = JSON.parse(value);
        return data &&
            Array.isArray(data.phases) &&
            Array.isArray(data.steps) &&
            data.phases.every(
                (phase: SetupDefinition["phases"][number]) =>
                    phase &&
                    typeof phase.id === "string" &&
                    phase.details &&
                    typeof phase.details.name === "string",
            ) &&
            data.steps.every(
                (step: SetupDefinition["steps"][number]) =>
                    step &&
                    typeof step.id === "string" &&
                    typeof step.phase_id === "string" &&
                    typeof step.count === "number",
            )
            ? data
            : null;
    } catch {
        return null;
    }
}
export function SetupDraft({
    value,
    onChange,
    review,
}: {
    value: string;
    onChange: (value: string) => void;
    review: boolean;
}) {
    const draft = setupDraft(value);
    const [editing, setEditing] = useState<string | null>(null);
    if (!draft) return <p>Add phases and steps to your schedule.</p>;
    const save = (next: SetupDefinition) => onChange(JSON.stringify(next));
    const update = (
        id: string,
        details: Partial<SetupDefinition["phases"][number]["details"]>,
    ) =>
        save({
            ...draft,
            phases: draft.phases.map((phase) =>
                phase.id === id
                    ? { ...phase, details: { ...phase.details, ...details } }
                    : phase,
            ),
        });
    const phases = draft.phases.map((phase) => ({
        id: phase.id,
        ...phase.details,
        count: 0,
        editHref: "",
        duplicateHref: "",
        deleteHref: "",
    })) as Phase[];
    if (review)
        return (
            <Table
                hover={false}
                className="border border-box-border [&_tbody_th]:font-semibold [&_tbody_th]:text-ink-900 dark:[&_tbody_th]:text-ink-100 [&_tbody_th]:whitespace-normal"
            >
                <caption className="pb-2 text-left font-semibold">
                    Phase pattern
                </caption>
                <tbody>
                    {draft.steps.map((step, index) => (
                        <tr key={step.id}>
                            <th scope="row" className="w-1/2">
                                {index + 1}.{" "}
                                {
                                    phases.find(
                                        (phase) => phase.id === step.phase_id,
                                    )?.name
                                }
                            </th>
                            <td className="text-right whitespace-nowrap">
                                {step.count}{" "}
                                {step.count === 1 ? "cycle" : "cycles"}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </Table>
        );
    return (
        <section className="space-y-3" aria-label="Customise campaign phases">
            <p className="text-sm text-muted">
                Edit each phase’s name, narrative, effects and rewards. These
                changes belong to your campaign.
            </p>
            <div className="flex flex-col gap-3">
                {draft.phases.map((phase, index) => (
                    <section
                        key={phase.id}
                        className="space-y-3 rounded border border-box-border p-3"
                    >
                        <Field
                            label={`Phase ${index + 1} name`}
                            htmlFor={`setup-phase-${index}`}
                        >
                            <Input
                                id={`setup-phase-${index}`}
                                required
                                maxLength={200}
                                value={phase.details.name}
                                onChange={(event) =>
                                    update(phase.id, {
                                        name: event.target.value,
                                    })
                                }
                            />
                        </Field>
                        <Button
                            size="sm"
                            variant="ghost"
                            aria-expanded={editing === phase.id}
                            aria-controls={`setup-details-${phase.id}`}
                            onClick={() =>
                                setEditing(
                                    editing === phase.id ? null : phase.id,
                                )
                            }
                        >
                            {editing === phase.id ? "Hide" : "Edit"} phase{" "}
                            {index + 1} details
                        </Button>
                        {editing === phase.id && (
                            <div
                                id={`setup-details-${phase.id}`}
                                className="space-y-4"
                            >
                                <Field
                                    label="Phase narrative"
                                    htmlFor={`setup-narrative-${phase.id}`}
                                >
                                    <Textarea
                                        maxLength={32000}
                                        value={phase.details.description}
                                        onChange={(event) =>
                                            update(phase.id, {
                                                description: event.target.value,
                                            })
                                        }
                                    />
                                </Field>
                                <Field
                                    label="Phase effects"
                                    htmlFor={`setup-effects-${phase.id}`}
                                >
                                    <Textarea
                                        maxLength={32000}
                                        value={phase.details.effects}
                                        onChange={(event) =>
                                            update(phase.id, {
                                                effects: event.target.value,
                                            })
                                        }
                                    />
                                </Field>
                                <RewardSettings
                                    value={JSON.stringify(
                                        phase.details.rewards,
                                    )}
                                    onChange={(rewards) =>
                                        update(phase.id, {
                                            rewards: JSON.parse(rewards),
                                        })
                                    }
                                />
                            </div>
                        )}
                    </section>
                ))}
                <div className="self-end">
                    <Button
                        size="sm"
                        variant="ghost"
                        className="inline-flex items-center gap-2 whitespace-nowrap"
                        onClick={() => {
                            const id = crypto
                                .randomUUID()
                                .replaceAll("-", "")
                                .slice(0, 26);
                            setEditing(id);
                            const reward = {
                                credits: { fixed: 0, dice: null },
                                reputation: 0,
                            };
                            save({
                                ...draft,
                                phases: [
                                    ...draft.phases,
                                    {
                                        id,
                                        details: {
                                            name: "New phase",
                                            description: "",
                                            effects: "",
                                            rewards: {
                                                win: reward,
                                                draw: reward,
                                                loss: reward,
                                                entry_credits: {
                                                    fixed: 0,
                                                    dice: null,
                                                },
                                            },
                                        },
                                    },
                                ],
                            });
                        }}
                    >
                        <Icon name="plus" /> Add phase
                    </Button>
                </div>
            </div>

            <PlanSteps
                value={JSON.stringify(draft.steps)}
                phases={phases}
                disabled={false}
                onChange={(steps) =>
                    save({ ...draft, steps: JSON.parse(steps) })
                }
            />
        </section>
    );
}
