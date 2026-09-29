import { useId, useState } from "react";
import { Field, Input, RadioCard, RadioCards } from "../../ui";

export type AdvancementRollProps = {
    mode: string;
    rolled: string;
    modeErrors: string[];
    rolledErrors: string[];
    previousRoll: number | null;
};

export function AdvancementRoll(props: AdvancementRollProps) {
    const id = useId();
    const [mode, setMode] = useState(props.mode);
    const [rolled, setRolled] = useState(props.rolled);
    return (
        <div className="space-y-5">
            {props.previousRoll !== null && (
                <p className="text-sm text-muted">
                    Recorded roll: {props.previousRoll}. Earlier rolls stay in
                    the history if you change it.
                </p>
            )}
            <RadioCards
                legend="Roll 2D6"
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
                label="Your 2D6 total"
                htmlFor={id}
                description="If you rolled your own dice, enter their total."
                errors={props.rolledErrors}
            >
                <Input
                    id={id}
                    name="rolled"
                    type="number"
                    min={2}
                    max={12}
                    inputMode="numeric"
                    disabled={mode !== "record"}
                    required={mode === "record"}
                    value={rolled}
                    onChange={(event) => setRolled(event.target.value)}
                />
            </Field>
        </div>
    );
}
