import { useId, useState } from "react";
import { Field, Input, RadioCard, RadioCards } from "../../ui";

export type RollChoiceOption = {
    value: string;
    label: string;
    /** Set when the next roll for this option reuses an earlier die. */
    carried: string;
};

export type RollChoices = {
    legend: string;
    name: string;
    value: string;
    errors: string[];
    options: RollChoiceOption[];
};

export type AdvancementRollProps = {
    dice: string;
    minimum: number;
    maximum: number;
    totalLabel: string;
    totalHelp: string;
    mode: string;
    rolled: string;
    modeErrors: string[];
    rolledErrors: string[];
    previousRoll: number | null;
    choices: RollChoices | null;
};

export function AdvancementRoll(props: AdvancementRollProps) {
    const id = useId();
    const [mode, setMode] = useState(props.mode);
    const [rolled, setRolled] = useState(props.rolled);
    const [choice, setChoice] = useState(props.choices?.value ?? "");
    const carried =
        props.choices?.options.find((option) => option.value === choice)
            ?.carried ?? "";
    return (
        <div className="space-y-5">
            {props.choices && (
                <RadioCards
                    legend={props.choices.legend}
                    min="min(100%, 18rem)"
                    errors={props.choices.errors}
                >
                    {props.choices.options.map((option) => (
                        <RadioCard
                            key={option.value}
                            name={props.choices!.name}
                            value={option.value}
                            label={option.label}
                            checked={choice === option.value}
                            onChange={() => setChoice(option.value)}
                        />
                    ))}
                </RadioCards>
            )}
            {props.previousRoll !== null && (
                <p className="text-sm text-muted">
                    Recorded roll: {props.previousRoll}. Earlier rolls stay in
                    the history if you change it.
                </p>
            )}
            {carried ? (
                <p className="text-sm text-muted">{carried}</p>
            ) : (
                <>
                    <RadioCards
                        legend={`Roll ${props.dice}`}
                        min="min(100%, 18rem)"
                        errors={props.modeErrors}
                    >
                        <RadioCard
                            name="roll_mode"
                            value="roll"
                            label="Roll in Gyrinx"
                            checked={mode === "roll"}
                            onChange={() => setMode("roll")}
                        />
                        <RadioCard
                            name="roll_mode"
                            value="record"
                            label="Record my roll"
                            checked={mode === "record"}
                            onChange={() => setMode("record")}
                        />
                    </RadioCards>
                    <Field
                        label={props.totalLabel}
                        htmlFor={id}
                        description={props.totalHelp}
                        errors={props.rolledErrors}
                    >
                        <Input
                            id={id}
                            name="rolled"
                            type="number"
                            min={props.minimum}
                            max={props.maximum}
                            inputMode="numeric"
                            disabled={mode !== "record"}
                            required={mode === "record"}
                            value={rolled}
                            onChange={(event) => setRolled(event.target.value)}
                        />
                    </Field>
                </>
            )}
        </div>
    );
}
