import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
    Button,
    ButtonLink,
    Dialog,
    Field,
    FormActions,
    Icon,
    NativeSelect,
} from "../../ui";

type Entry = {
    roll: number;
    name: string;
    text: string;
    parts?: [string, boolean][];
    image: string;
};

type SideJobSet = {
    key: string;
    name: string;
    label: string;
    entries: Entry[];
};

// A side job's result also names its set, so it can be rolled again.
type Result = { key: string; heading: string; entry: Entry; set?: string };

// A side job pick: "" until a set is picked, "leave", a set's key to
// roll on it, or a set's key and roll for one of its jobs, "escher-3".
function setOf(pick: string, sets: SideJobSet[]) {
    return sets.find((found) => found.key === pick.split("-")[0]);
}

function Text({ entry }: { entry: Entry }) {
    return (
        <>
            {(entry.parts ?? [[entry.text, false]]).map(
                ([words, bold], index) =>
                    bold ? <strong key={index}>{words}</strong> : words,
            )}
        </>
    );
}

export type BattleScenarioProps = {
    rollUrl: string;
    save?: {
        action: string;
        csrfToken: string;
        campaign: string;
        battle: string;
        revision: number;
        printUrl: string;
    };
    rolls: Record<string, string>;
    tables: {
        key: string;
        name: string;
        entries: Entry[];
    }[];
    sideJobKeys?: string[];
    sideJobLimit?: number;
    sideJobSets?: SideJobSet[];
};

export function BattleScenario(props: BattleScenarioProps) {
    const [rolls, setRolls] = useState(props.rolls);
    const [revision, setRevision] = useState(props.save?.revision);
    const [picks, setPicks] = useState<Record<string, string>>({});
    const [sidePicks, setSidePicks] = useState<string[]>([""]);
    const sideJobKeys = props.sideJobKeys ?? [];
    const sideJobSets = props.sideJobSets ?? [];
    const [pending, setPending] = useState(false);
    const [error, setError] = useState("");
    // The side job whose Reroll dialog is open, and the set picked in it.
    const [reroll, setReroll] = useState<{
        key: string;
        heading: string;
        set: string;
    } | null>(null);
    const root = useRef<HTMLElement>(null);
    const request = useRef<AbortController | null>(null);
    useEffect(() => {
        const form = props.save ? null : root.current?.closest("form");
        const guard = (event: Event) => {
            if (request.current) {
                event.preventDefault();
                setError("Wait for the scenario to finish generating.");
            }
        };
        form?.addEventListener("submit", guard);
        return () => {
            form?.removeEventListener("submit", guard);
            request.current?.abort();
        };
    }, [props.save]);
    let invalid = props.tables.some(
        (table) =>
            rolls[table.key] &&
            !table.entries.some(
                (entry) => String(entry.roll) === rolls[table.key],
            ),
    );
    const found: Result[] = props.tables.flatMap((table) => {
        const entry = table.entries.find(
            (entry) => String(entry.roll) === rolls[table.key],
        );
        return entry ? [{ key: table.key, heading: table.name, entry }] : [];
    });
    // Side jobs are stored as a set and roll, "escher-3"; a bare roll is
    // from the General set, as battles saved before there were sets have.
    let place = 0;
    for (const key of sideJobKeys) {
        const value = rolls[key];
        if (!value) continue;
        place += 1;
        const [setKey, roll] = value.includes("-")
            ? value.split("-")
            : ["general", value];
        const set = sideJobSets.find((found) => found.key === setKey);
        const entry = set?.entries.find((entry) => String(entry.roll) === roll);
        if (!set || !entry) invalid = true;
        else
            found.push({
                key,
                heading: `Side job ${place} (${set.name})`,
                entry,
                set: set.key,
            });
    }
    const results = invalid ? [] : found;
    const query = new URLSearchParams(
        Object.entries(rolls).filter(([, value]) => value),
    );
    // The menus as they are set, for Generate.
    function menuChoices() {
        const choices = new URLSearchParams({ generate: "1", format: "json" });
        for (const [key, value] of Object.entries(picks))
            choices.set(key + "_pick", value);
        if (sideJobKeys.length) {
            sidePicks.forEach((pick, index) => {
                if (pick) choices.set(sideJobKeys[index] + "_pick", pick);
            });
            choices.set("side_jobs", String(sidePicks.length));
        }
        return choices;
    }
    // The scenario as it is, but with one side job rolled on another set.
    function rerollChoices(target: string, set: string) {
        const choices = new URLSearchParams({ generate: "1", format: "json" });
        for (const table of props.tables)
            choices.set(table.key + "_pick", rolls[table.key] || "leave");
        const sideJobs = results.filter((result) => result.set);
        sideJobs.forEach((result, index) =>
            choices.set(
                sideJobKeys[index] + "_pick",
                result.key === target
                    ? set
                    : `${result.set}-${result.entry.roll}`,
            ),
        );
        choices.set("side_jobs", String(sideJobs.length));
        return choices;
    }
    // After a reroll, the menu that gave that side job rolls on its new
    // set too, when each menu with a set still gave one side job.
    function pickRerolledSet(target: string, set: string) {
        const sideJobs = results.filter((result) => result.set);
        const giving = sidePicks.flatMap((pick, index) =>
            pick && pick !== "leave" ? [index] : [],
        );
        if (giving.length !== sideJobs.length) return;
        const at = giving[sideJobs.findIndex((r) => r.key === target)];
        setSidePicks(
            sidePicks.map((pick, index) => (index === at ? set : pick)),
        );
    }
    async function generate(
        choices = menuChoices(),
        done: () => void = () => {},
    ) {
        if (request.current) return;
        const controller = new AbortController();
        request.current = controller;
        setPending(true);
        setError("");
        const failure = props.save
            ? "The scenario could not be attached. Reload the battle and try again."
            : "The scenario could not be generated. Try again.";
        try {
            let response: Response;
            if (props.save) {
                const body = new FormData();
                for (const [key, value] of choices) body.set(key, value);
                body.set("csrfmiddlewaretoken", props.save.csrfToken);
                body.set("campaign", props.save.campaign);
                body.set("battle", props.save.battle);
                body.set("revision", String(revision));
                response = await fetch(props.save.action, {
                    method: "POST",
                    body,
                    signal: controller.signal,
                    headers: { Accept: "application/json" },
                });
            } else {
                const url = new URL(props.rollUrl, window.location.href);
                url.search = choices.toString();
                response = await fetch(url.href, {
                    signal: controller.signal,
                    headers: { Accept: "application/json" },
                });
            }
            if (
                !response.headers
                    .get("content-type")
                    ?.includes("application/json")
            )
                throw new Error();
            const data = await response.json();
            if (!response.ok) {
                setError(data.errors?.join(" ") || failure);
                return;
            }
            setError("");
            if (props.save) setRevision(data.revision);
            setRolls(
                Object.fromEntries(
                    Object.entries(data.rolls).map(([key, value]) => [
                        key,
                        String(value),
                    ]),
                ),
            );
            done();
        } catch {
            if (!controller.signal.aborted) setError(failure);
        } finally {
            request.current = null;
            if (!controller.signal.aborted) setPending(false);
        }
    }
    return (
        <section
            ref={root}
            className="space-y-3"
            aria-label="Generated scenario"
            aria-busy={pending}
        >
            {[...props.tables.map((table) => table.key), ...sideJobKeys].map(
                (key) => (
                    <input
                        key={key}
                        type="hidden"
                        name={key}
                        value={rolls[key] ?? ""}
                    />
                ),
            )}
            {results.length > 0 && (
                <>
                    {!props.save && <h3 className="font-semibold">Scenario</h3>}
                    <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                        {results.map(({ key, heading, entry }) => (
                            <div key={key}>
                                <dt className="text-muted">{heading}</dt>
                                <dd className="font-medium">{entry.name}</dd>
                            </div>
                        ))}
                    </dl>
                    <details>
                        <summary className="cursor-pointer text-sm font-medium">
                            Full details
                        </summary>
                        <div className="mt-3 space-y-3">
                            {results.map(({ key, heading, entry, set }) => (
                                <div key={key}>
                                    <div className="flex flex-wrap items-baseline gap-x-3">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
                                            {heading}
                                        </p>
                                        {set && (
                                            <Button
                                                variant="text"
                                                className="text-sm"
                                                disabled={pending}
                                                aria-label={`Reroll ${heading}`}
                                                onClick={() =>
                                                    setReroll({
                                                        key,
                                                        heading,
                                                        set,
                                                    })
                                                }
                                            >
                                                Reroll
                                            </Button>
                                        )}
                                    </div>
                                    <h4 className="font-semibold">
                                        {entry.name}
                                    </h4>
                                    <p className="text-sm">
                                        <Text entry={entry} />
                                    </p>
                                    {entry.image && (
                                        <img
                                            className="mt-2 w-full max-w-sm"
                                            src={entry.image}
                                            alt={`${heading}: ${entry.name}`}
                                        />
                                    )}
                                </div>
                            ))}
                        </div>
                    </details>
                </>
            )}
            <details>
                <summary className="cursor-pointer text-sm font-medium">
                    Scenario options
                </summary>
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {props.tables.map((table) => (
                        <Field
                            key={table.key}
                            label={table.name}
                            htmlFor={`preview-${table.key}`}
                        >
                            <NativeSelect
                                disabled={pending}
                                value={picks[table.key] ?? "roll"}
                                onChange={(event) =>
                                    setPicks({
                                        ...picks,
                                        [table.key]: event.target.value,
                                    })
                                }
                            >
                                <option value="roll">Roll a D6</option>
                                <option value="leave">Leave out</option>
                                {table.entries.map((entry) => (
                                    <option key={entry.roll} value={entry.roll}>
                                        {entry.name}
                                    </option>
                                ))}
                            </NativeSelect>
                        </Field>
                    ))}
                    {sideJobKeys.length > 0 &&
                        sidePicks.map((pick, index) => {
                            const set = setOf(pick, sideJobSets);
                            const id = `preview-${sideJobKeys[index]}`;
                            return (
                                <Field
                                    key={index}
                                    label={
                                        set
                                            ? `Side job ${index + 1}: ${set.label}`
                                            : `Side job ${index + 1}`
                                    }
                                    htmlFor={id}
                                >
                                    <div className="flex items-center gap-2">
                                        <div className="min-w-0 flex-1">
                                            <NativeSelect
                                                id={id}
                                                disabled={pending}
                                                value={pick}
                                                onChange={(event) =>
                                                    setSidePicks(
                                                        sidePicks.map(
                                                            (each, at) =>
                                                                at === index
                                                                    ? event
                                                                          .target
                                                                          .value
                                                                    : each,
                                                        ),
                                                    )
                                                }
                                            >
                                                {set ? (
                                                    <>
                                                        <option value={set.key}>
                                                            Roll a D6
                                                        </option>
                                                        {set.entries.map(
                                                            (entry) => (
                                                                <option
                                                                    key={
                                                                        entry.roll
                                                                    }
                                                                    value={`${set.key}-${entry.roll}`}
                                                                >
                                                                    {`${entry.roll}. ${entry.name}`}
                                                                </option>
                                                            ),
                                                        )}
                                                        <option value="">
                                                            Change set
                                                        </option>
                                                    </>
                                                ) : (
                                                    <>
                                                        <option value="">
                                                            Choose a side job
                                                            set
                                                        </option>
                                                        <option value="leave">
                                                            Leave out
                                                        </option>
                                                        {sideJobSets.map(
                                                            (each) => (
                                                                <option
                                                                    key={
                                                                        each.key
                                                                    }
                                                                    value={
                                                                        each.key
                                                                    }
                                                                >
                                                                    {each.label}
                                                                </option>
                                                            ),
                                                        )}
                                                    </>
                                                )}
                                            </NativeSelect>
                                        </div>
                                        {index > 0 && (
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                disabled={pending}
                                                aria-label={`Remove side job ${index + 1}`}
                                                title={`Remove side job ${index + 1}`}
                                                onClick={() =>
                                                    setSidePicks(
                                                        sidePicks.filter(
                                                            (_, at) =>
                                                                at !== index,
                                                        ),
                                                    )
                                                }
                                            >
                                                <Icon name="trash-2" />
                                            </Button>
                                        )}
                                    </div>
                                </Field>
                            );
                        })}
                </div>
                {sideJobKeys.length > 0 &&
                    sidePicks.length < (props.sideJobLimit ?? 6) && (
                        <Button
                            size="sm"
                            className="mt-3"
                            disabled={pending}
                            onClick={() => setSidePicks([...sidePicks, ""])}
                        >
                            + Add side job
                        </Button>
                    )}
            </details>
            {error && (
                <p
                    role="alert"
                    className="text-sm text-red-600 dark:text-red-400"
                >
                    {error}
                </p>
            )}
            <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => generate()} disabled={pending} size="sm">
                    {pending
                        ? "Generating…"
                        : results.length
                          ? "Generate again"
                          : "Generate scenario"}
                </Button>
                {results.length > 0 && (
                    <>
                        {!props.save && (
                            <Button
                                onClick={() => setRolls({})}
                                disabled={pending}
                                size="sm"
                            >
                                Remove scenario
                            </Button>
                        )}
                        {props.save && (
                            <ButtonLink
                                href={`${props.save.printUrl}?${query}`}
                                size="sm"
                                target="_blank"
                                rel="noopener"
                            >
                                Print
                            </ButtonLink>
                        )}
                        <ButtonLink
                            href={`${props.rollUrl}?${query}`}
                            size="sm"
                            target="_blank"
                            rel="noopener"
                        >
                            View scenario
                        </ButtonLink>
                    </>
                )}
            </div>
            {/* On the battle form this panel sits inside the page's form,
                and a dialog's form may not nest in it. */}
            {reroll &&
                createPortal(
                    <Dialog
                        title={`Reroll ${reroll.heading.split(" (")[0].toLowerCase()}`}
                        lead="Choose the set to roll on. The rest of the scenario stays the same."
                        onDismiss={() => setReroll(null)}
                        onSubmit={(event) => {
                            event.preventDefault();
                            const { key, set } = reroll;
                            setReroll(null);
                            generate(rerollChoices(key, set), () =>
                                pickRerolledSet(key, set),
                            );
                        }}
                    >
                        <Field label="Side job set" htmlFor="reroll-set">
                            <NativeSelect
                                id="reroll-set"
                                value={reroll.set}
                                onChange={(event) =>
                                    setReroll({
                                        ...reroll,
                                        set: event.target.value,
                                    })
                                }
                            >
                                {sideJobSets.map((each) => (
                                    <option key={each.key} value={each.key}>
                                        {each.label}
                                    </option>
                                ))}
                            </NativeSelect>
                        </Field>
                        <FormActions>
                            <Button
                                variant="ghost"
                                onClick={() => setReroll(null)}
                            >
                                Cancel
                            </Button>
                            <Button type="submit" variant="success">
                                Reroll
                            </Button>
                        </FormActions>
                    </Dialog>,
                    document.body,
                )}
        </section>
    );
}
