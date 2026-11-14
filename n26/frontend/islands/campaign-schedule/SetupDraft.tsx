import { useState, type ReactNode } from "react";
import { Button, Card, Field, Icon, Input, Table, Textarea } from "../../ui";
import { PhaseSummary } from "./PhaseSummary";
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
    cyclesOptions,
    mode,
}: {
    value: string;
    onChange: (value: string) => void;
    review: boolean;
    cyclesOptions?: ReactNode;
    mode?: string;
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
        <section className="space-y-6" aria-label="Customise campaign phases">
            <section
                aria-labelledby="setup-phases-heading"
                className="space-y-3"
            >
                <h2 id="setup-phases-heading" className="text-lg font-semibold">
                    Phases
                </h2>
                <p className="text-sm text-muted">
                    Edit each phase’s name, description, effects and rewards.
                    These changes belong to your campaign.
                </p>
                <div className="flex flex-col gap-3">
                    {draft.phases.map((phase, index) => (
                        <section
                            key={phase.id}
                            aria-labelledby={`setup-heading-${phase.id}`}
                        >
                            <Card
                                header={
                                    <h3 id={`setup-heading-${phase.id}`}>
                                        Phase {index + 1}
                                    </h3>
                                }
                            >
                                <div className="space-y-3">
                                    <Field
                                        label="Name"
                                        htmlFor={`setup-phase-${index}`}
                                    >
                                        <Input
                                            id={`setup-phase-${index}`}
                                            aria-label={`Phase ${index + 1} name`}
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
                                    <PhaseSummary
                                        {...phase.details}
                                        showName={false}
                                    />
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        aria-label={`${editing === phase.id ? "Hide" : "Edit"} phase ${index + 1} details`}
                                        aria-expanded={editing === phase.id}
                                        aria-controls={`setup-details-${phase.id}`}
                                        onClick={() =>
                                            setEditing(
                                                editing === phase.id
                                                    ? null
                                                    : phase.id,
                                            )
                                        }
                                    >
                                        <Icon name="pencil" />
                                        {editing === phase.id
                                            ? "Hide details"
                                            : "Edit details"}
                                        <Icon
                                            name="chevron-down"
                                            className={`size-4 transition-transform ${editing === phase.id ? "rotate-180" : ""}`}
                                        />
                                    </Button>
                                    {editing === phase.id && (
                                        <div
                                            id={`setup-details-${phase.id}`}
                                            className="space-y-4"
                                        >
                                            <Field
                                                label="Description"
                                                htmlFor={`setup-narrative-${phase.id}`}
                                            >
                                                <Textarea
                                                    id={`setup-narrative-${phase.id}`}
                                                    aria-label={`Phase ${index + 1} description`}
                                                    maxLength={32000}
                                                    value={
                                                        phase.details
                                                            .description
                                                    }
                                                    onChange={(event) =>
                                                        update(phase.id, {
                                                            description:
                                                                event.target
                                                                    .value,
                                                        })
                                                    }
                                                />
                                            </Field>
                                            <Field
                                                label="Effects"
                                                htmlFor={`setup-effects-${phase.id}`}
                                            >
                                                <Textarea
                                                    id={`setup-effects-${phase.id}`}
                                                    aria-label={`Phase ${index + 1} effects`}
                                                    maxLength={32000}
                                                    value={
                                                        phase.details.effects
                                                    }
                                                    onChange={(event) =>
                                                        update(phase.id, {
                                                            effects:
                                                                event.target
                                                                    .value,
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
                                                        rewards:
                                                            JSON.parse(rewards),
                                                    })
                                                }
                                            />
                                        </div>
                                    )}
                                </div>
                            </Card>
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
            </section>
            <section
                aria-labelledby="setup-cycles-heading"
                className="space-y-3"
            >
                <h2 id="setup-cycles-heading" className="text-lg font-semibold">
                    Cycles
                </h2>
                {cyclesOptions}
                <Card>
                    <section
                        aria-label={
                            mode === "repeating"
                                ? "Repeating pattern options"
                                : "Fixed plan options"
                        }
                    >
                        <p className="mb-3 text-sm text-muted">
                            {mode === "repeating"
                                ? "Choose the cycle steps to repeat."
                                : "Choose the cycle steps for this campaign."}
                        </p>
                        <PlanSteps
                            value={JSON.stringify(draft.steps)}
                            phases={phases}
                            disabled={false}
                            onChange={(steps) =>
                                save({ ...draft, steps: JSON.parse(steps) })
                            }
                        />
                    </section>
                </Card>
            </section>
        </section>
    );
}
