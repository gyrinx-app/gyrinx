import { useId, useState } from "react";
import { Field, Input, RadioCard, RadioCards } from "../../ui";

export type CampaignRollSourceProps = {
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
    const physical = source === "manual";
    return (
        <div className="space-y-5">
            <RadioCards
                legend="How to roll *"
                min="min(100%, 9rem)"
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
                    />
                ))}
            </RadioCards>
            <Field
                label="Physical result"
                htmlFor={id}
                description="Enter the result of your physical dice."
                errors={props.rolledErrors}
            >
                <Input
                    id={id}
                    name="rolled"
                    type="number"
                    min={1}
                    max={66}
                    inputMode="numeric"
                    disabled={!physical}
                    required={physical}
                    value={rolled}
                    onChange={(event) => setRolled(event.target.value)}
                />
            </Field>
        </div>
    );
}
