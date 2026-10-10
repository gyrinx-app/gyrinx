import { useId, useLayoutEffect, useRef, useState } from "react";
import { Field, Input } from "../../ui";

type RollField = {
    label: string;
    helpText: string;
    value: string;
    errors: string[];
};

export type PoolRollProps = {
    count: RollField;
    rolled: RollField;
    ranges: string[];
    focusedField?: string;
};

export function PoolRoll(props: PoolRollProps) {
    const [count, setCount] = useState(
        props.rolled.value !== "" ? "1" : props.count.value,
    );
    const [rolled, setRolled] = useState(props.rolled.value);
    const countRef = useRef<HTMLInputElement>(null);
    const rollRef = useRef<HTMLInputElement>(null);
    const manual = rolled !== "";
    const rangesId = useId();

    useLayoutEffect(() => {
        if (props.focusedField === "count") countRef.current?.focus();
        if (props.focusedField === "rolled") rollRef.current?.focus();
    }, [props.focusedField]);

    return (
        <>
            <Field
                label={props.count.label}
                htmlFor="pool-count"
                errors={props.count.errors}
                description={
                    manual
                        ? "Your own roll adds one result. Clear ‘Your own roll’ to roll more."
                        : props.count.helpText
                }
            >
                <Input
                    ref={countRef}
                    id="pool-count"
                    name="count"
                    type="number"
                    min={1}
                    max={100}
                    required
                    inputMode="numeric"
                    value={manual ? "1" : count}
                    readOnly={manual}
                    onChange={(event) => setCount(event.target.value)}
                />
            </Field>
            <Field
                label={props.rolled.label}
                htmlFor="pool-roll"
                errors={props.rolled.errors}
                description={props.rolled.helpText}
            >
                <Input
                    ref={rollRef}
                    id="pool-roll"
                    name="rolled"
                    type="number"
                    min={1}
                    inputMode="numeric"
                    autoComplete="off"
                    aria-describedby={rangesId}
                    value={rolled}
                    onChange={(event) => {
                        setRolled(event.target.value);
                        if (event.target.value !== "") setCount("1");
                    }}
                />
            </Field>
            <div id={rangesId} className="text-sm text-muted">
                {props.ranges.map((range, index) => (
                    <p key={index}>{range}</p>
                ))}
            </div>
        </>
    );
}
