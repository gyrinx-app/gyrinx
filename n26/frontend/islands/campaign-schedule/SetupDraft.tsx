import { Button, Field, Icon, Input } from "../../ui";
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
    if (!draft) return <p>Choose a starting template to preview its phases.</p>;
    const save = (next: SetupDefinition) => onChange(JSON.stringify(next));
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
            <ol className="divide-y divide-box-border border border-box-border">
                {draft.steps.map((step, index) => (
                    <li
                        key={step.id}
                        className="flex justify-between gap-3 px-3 py-2 text-sm"
                    >
                        <span>
                            {index + 1}.{" "}
                            {
                                phases.find(
                                    (phase) => phase.id === step.phase_id,
                                )?.name
                            }
                        </span>
                        <span className="shrink-0">
                            {step.count} {step.count === 1 ? "cycle" : "cycles"}
                        </span>
                    </li>
                ))}
            </ol>
        );
    return (
        <section className="space-y-3" aria-label="Customise campaign phases">
            <p className="text-sm text-muted">
                These changes belong to your campaign. The starting template
                stays unchanged.
            </p>
            <div className="flex flex-col gap-3">
                {draft.phases.map((phase, index) => (
                    <Field
                        key={phase.id}
                        label={`Phase ${index + 1} name`}
                        htmlFor={`setup-phase-${index}`}
                    >
                        <Input
                            id={`setup-phase-${index}`}
                            required
                            maxLength={200}
                            value={phase.details.name}
                            onChange={(event) =>
                                save({
                                    ...draft,
                                    phases: draft.phases.map((item) =>
                                        item.id === phase.id
                                            ? {
                                                  ...item,
                                                  details: {
                                                      ...item.details,
                                                      name: event.target.value,
                                                  },
                                              }
                                            : item,
                                    ),
                                })
                            }
                        />
                    </Field>
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
