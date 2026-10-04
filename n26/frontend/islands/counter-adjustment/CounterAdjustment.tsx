import { useId, useState } from "react";
import { Field, Input } from "../../ui";

export type CounterAdjustmentProps = {
    value: number;
    recorded: number;
    change: string;
    errors: string[];
    maximum: number;
};

export function CounterAdjustment(props: CounterAdjustmentProps) {
    const id = useId();
    const [change, setChange] = useState(props.change);
    const amount = change.trim() === "" ? 0 : Number(change);
    const valid = Number.isInteger(amount) && Math.abs(amount) <= props.maximum;
    const delta = valid ? Math.max(-props.recorded, amount) : 0;
    const value = props.value + delta;
    return (
        <div className="space-y-5">
            <div
                className="space-y-1 text-center"
                aria-live="polite"
                aria-atomic="true"
            >
                <p className="text-sm text-muted">Value</p>
                <p
                    className="text-4xl font-semibold tabular-nums"
                    data-counter-preview
                >
                    {value}
                </p>
                <p
                    className="text-sm tabular-nums text-muted"
                    data-counter-delta
                >
                    {delta >= 0 ? "+" : ""}
                    {delta}
                </p>
            </div>
            <Field
                label="Change *"
                htmlFor={id}
                errors={props.errors}
                description="Use a positive number to add or a negative number to remove."
            >
                <Input
                    id={id}
                    name="change"
                    type="number"
                    required
                    min={-props.maximum}
                    max={props.maximum}
                    value={change}
                    onChange={(event) => setChange(event.target.value)}
                />
            </Field>
        </div>
    );
}
