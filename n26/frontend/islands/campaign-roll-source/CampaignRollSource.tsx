import { useEffect, useId, useState } from "react";
import { Field, Input, RadioCard, RadioCards } from "../../ui";

export type CampaignRollSourceProps = {
    requestKey: string;
    source: string;
    rolled: string;
    choices: { value: string; label: string }[];
    sourceErrors: string[];
    rolledErrors: string[];
};

export function CampaignRollSource(props: CampaignRollSourceProps) {
    const id = useId();
    const [source, setSource] = useState(props.source);
    const [rolled, setRolled] = useState(props.rolled);
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
    return (
        <div className="space-y-5">
            <input type="hidden" name="request_key" value={requestKey} />
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
                                label="Result"
                                htmlFor={id}
                                errors={props.rolledErrors}
                            >
                                <Input
                                    id={id}
                                    name="rolled"
                                    type="number"
                                    min={1}
                                    max={66}
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
        </div>
    );
}
