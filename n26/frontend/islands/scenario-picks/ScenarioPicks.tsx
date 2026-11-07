import { Field, NativeSelect } from "../../ui";
import { SideJobFields, type SideJobSet } from "../../scenarios/SideJobFields";
import { useScenarioPicks } from "../../scenarios/useScenarioPicks";

export type ScenarioPicksProps = {
    tables: { key: string; label: string; choices: [string, string][] }[];
    sideJobKeys: string[];
    sideJobLimit: number;
    sideJobSets: SideJobSet[];
    referencedSideJobSets?: SideJobSet[];
    sidePicks: string[];
    errors: Record<string, string[]>;
};

export function ScenarioPicks(props: ScenarioPicksProps) {
    const { picks, sidePicks, setPicks, setSidePicks } = useScenarioPicks({
        tableKeys: props.tables.map((table) => table.key),
        sideJobKeys: props.sideJobKeys,
        limit: props.sideJobLimit,
        initialSidePicks: props.sidePicks,
    });
    return (
        <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
                {props.tables.map((table) => (
                    <Field
                        key={table.key}
                        label={table.label}
                        htmlFor={`generator-${table.key}`}
                        errors={props.errors[`${table.key}_pick`]}
                    >
                        <NativeSelect
                            id={`generator-${table.key}`}
                            name={`${table.key}_pick`}
                            value={picks[table.key]}
                            onChange={(event) =>
                                setPicks({
                                    ...picks,
                                    [table.key]: event.target.value,
                                })
                            }
                        >
                            {table.choices.map(([value, label]) => (
                                <option key={value} value={value}>
                                    {label}
                                </option>
                            ))}
                        </NativeSelect>
                    </Field>
                ))}
            </div>
            <SideJobFields
                prefix="generator"
                picks={sidePicks}
                sets={props.sideJobSets}
                referencedSets={props.referencedSideJobSets}
                keys={props.sideJobKeys}
                limit={props.sideJobLimit}
                onChange={setSidePicks}
                errors={props.errors}
                submitNames
            />
            <input type="hidden" name="side_jobs" value={sidePicks.length} />
        </div>
    );
}
