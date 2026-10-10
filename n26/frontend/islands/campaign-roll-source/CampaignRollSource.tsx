import { useEffect, useId, useState } from "react";
import { Field, Input, RadioCard, RadioCards } from "../../ui";

export type CampaignRollSourceProps = {
    requestKey: string;
    source: string;
    rolled: string;
    choices: { value: string; label: string }[];
    sourceErrors: string[];
    rolledErrors: string[];
    count: string;
    countErrors: string[];
    maxDice: number;
    modifier: string;
    modifierErrors: string[];
    modifierApplication: string;
    modifierApplicationErrors: string[];
    modifierChoices: { value: string; label: string }[];
};

export function CampaignRollSource(props: CampaignRollSourceProps) {
    const id = useId();
    const [source, setSource] = useState(props.source);
    const [rolled, setRolled] = useState(props.rolled);
    const [count, setCount] = useState(props.count);
    const [modifier, setModifier] = useState(props.modifier);
    const [application, setApplication] = useState(props.modifierApplication);
    const [requestKey, setRequestKey] = useState(props.requestKey);
    useEffect(() => {
        // A restored form starts a new submission; retries of its POST keep
        // the same key until the browser returns from the result page.
        const restored = (event: PageTransitionEvent) => {
            if (event.persisted) setRequestKey(crypto.randomUUID());
        };
        window.addEventListener("pageshow", restored);
        return () => window.removeEventListener("pageshow", restored);
    }, []);
    const manual = source === "manual";
    const quantity = Number(count);
    const boundedCount = Math.min(props.maxDice, Math.max(1, quantity || 1));
    return (
        <div className="space-y-5">
            <input type="hidden" name="request_key" value={requestKey} />
            <Field
                label="Number of dice *"
                htmlFor={`${id}-count`}
                errors={props.countErrors}
            >
                <Input
                    id={`${id}-count`}
                    name="count"
                    type="number"
                    min={1}
                    max={props.maxDice}
                    inputMode="numeric"
                    required
                    className="max-w-32"
                    value={count}
                    onChange={(event) => setCount(event.target.value)}
                />
            </Field>
            <RadioCards
                legend="How to roll *"
                min="min(100%, 18rem)"
                errors={props.sourceErrors}
            >
                {props.choices.map((choice) => (
                    <RadioCard
                        key={choice.value}
                        name="source"
                        value={choice.value}
                        label={choice.label}
                        checked={source === choice.value}
                        onChange={() => setSource(choice.value)}
                    >
                        {choice.value === "manual" && (
                            <Field
                                label={
                                    quantity > 1
                                        ? "Total before modifiers"
                                        : "Result if already rolled"
                                }
                                htmlFor={`${id}-result`}
                                errors={props.rolledErrors}
                            >
                                <Input
                                    id={`${id}-result`}
                                    name="rolled"
                                    type="number"
                                    min={boundedCount}
                                    max={66 * boundedCount}
                                    inputMode="numeric"
                                    disabled={!manual}
                                    required={manual}
                                    value={rolled}
                                    onChange={(event) =>
                                        setRolled(event.target.value)
                                    }
                                />
                            </Field>
                        )}
                    </RadioCard>
                ))}
            </RadioCards>
            <Field
                label="Modifier"
                htmlFor={`${id}-modifier`}
                errors={props.modifierErrors}
            >
                <Input
                    id={`${id}-modifier`}
                    name="modifier"
                    type="number"
                    min={-2147483648}
                    max={2147483647}
                    placeholder="0"
                    value={modifier}
                    onChange={(event) => setModifier(event.target.value)}
                />
                <p className="mt-2 text-sm text-muted">
                    A positive or negative whole number. Leave blank for no
                    modifier.
                </p>
            </Field>
            <RadioCards
                legend="Apply modifier to"
                min="min(100%, 12rem)"
                errors={props.modifierApplicationErrors}
            >
                {props.modifierChoices.map((choice) => (
                    <RadioCard
                        key={choice.value}
                        name="modifier_application"
                        value={choice.value}
                        label={choice.label}
                        checked={application === choice.value}
                        onChange={() => setApplication(choice.value)}
                    />
                ))}
            </RadioCards>
            {quantity > 1 && application === "each" && (
                <p className="text-sm text-muted">
                    The total includes the modifier once for each die.
                </p>
            )}
        </div>
    );
}
