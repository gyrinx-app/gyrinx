import { useId, useState } from "react";
import { Field, NativeSelect } from "../../ui";

export type CampaignRollAttributionProps = {
    gang: string;
    miniature: string;
    gangErrors: string[];
    miniatureErrors: string[];
    gangs: { value: string; label: string }[];
    models: { value: string; label: string; gang: string }[];
};

export function CampaignRollAttribution(props: CampaignRollAttributionProps) {
    const id = useId();
    const [gang, setGang] = useState(props.gang);
    const [miniature, setMiniature] = useState(props.miniature);
    const models = props.models.filter((model) => model.gang === gang);
    return (
        <div className="space-y-5">
            <Field
                label="Gang"
                htmlFor={`${id}-gang`}
                errors={props.gangErrors}
            >
                <NativeSelect
                    id={`${id}-gang`}
                    name="gang"
                    value={gang}
                    onChange={(event) => {
                        setGang(event.target.value);
                        setMiniature("");
                    }}
                >
                    <option value="">No related gang</option>
                    {props.gangs.map((option) => (
                        <option key={option.value} value={option.value}>
                            {option.label}
                        </option>
                    ))}
                </NativeSelect>
            </Field>
            <Field
                label="Model"
                htmlFor={`${id}-model`}
                errors={props.miniatureErrors}
                description={
                    !gang
                        ? "Select a gang to link this roll to a model."
                        : models.length === 0
                          ? "No models in this gang."
                          : "Optional. Select a model from this gang."
                }
            >
                <NativeSelect
                    id={`${id}-model`}
                    name="miniature"
                    value={miniature}
                    disabled={!gang}
                    onChange={(event) => setMiniature(event.target.value)}
                >
                    <option value="">No related model</option>
                    {models.map((option) => (
                        <option key={option.value} value={option.value}>
                            {option.label}
                        </option>
                    ))}
                </NativeSelect>
            </Field>
        </div>
    );
}
