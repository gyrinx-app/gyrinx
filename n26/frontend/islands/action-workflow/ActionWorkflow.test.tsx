import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ActionWorkflow, type ActionWorkflowProps } from "./ActionWorkflow";

const props: ActionWorkflowProps = {
    title: "Advancement",
    modelName: "Mara",
    gangName: "Test gang",
    gangHref: "/gang/",
    modelHref: "/model/",
    facts: {
        stage: "roll",
        submit_label: "Continue",
        submit_variant: "primary",
        outcome: "Gain advancement",
        allowanceThreshold: true,
        steps: [{ label: "Roll", current: true }],
        prices: [],
        payments: [],
        receipt: [],
        outcomes: [],
        items: [],
        advancements: [],
        skillGroups: [],
        attempts: [],
        reviewChoice: null,
        changes: [],
        skillRoll: null,
        roll: {
            dice: "2D6",
            minimum: 2,
            maximum: 12,
            totalLabel: "Your 2D6 total",
            totalHelp: "Enter their total.",
            mode: "roll",
            rolled: "",
            modeErrors: [],
            rolledErrors: [],
            previousRoll: null,
            choices: null,
        },
    },
    values: {
        draft_key: "draft:record:roll",
        gang_id: "gang",
        command_key: "command-one",
        revision: "1",
        target_kind: "flow",
        target_id: "record",
        target_step: "roll",
        target_allowance: "",
        target_allowance_present: "0",
        target_pick_present: "0",
        target_pick: "",
        submitted_summary: "",
        request_key: "roll-one",
        previous_roll: "",
        roll_mode: "roll",
        rolled: "",
        skill_set_id: "",
    },
    errors: {},
    initialConflict: false,
    fields: ["request_key", "roll_mode", "rolled", "previous_roll"],
    hiddenFields: ["request_key", "previous_roll"],
    action: "/flow/roll/",
    commandHref: "/command/",
    displayHref: "/display/",
    csrfToken: "fresh",
    recoveryKey: "actor:gang:model",
    draftKey: "draft:record:roll",
    draftScope: "draft:",
    recoveryHref: "/flow/roll/?recover=1&gang_id=gang",
    signInHref: "/login/?next=flow",
};
const saved = {
    action: "Advancement",
    record: "record",
    revision: 2,
    state: "started",
    outcome: "Gain advancement",
    selection: "Dodge",
    rolls: [{ roll: 11, dice: "2d6" }],
    attempts: [{ result_name: "Dodge" }],
};
const json = (data: unknown, status = 200) => ({
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => data,
});
afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionStorage.clear();
    window.history.replaceState(null, "", "/");
});

test("the default rolled radio is selected and the disabled entered total is omitted", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValue(
            json({ saved: true, facts: saved, nextUrl: "/choose/" }),
        );
    vi.stubGlobal("fetch", fetch);
    render(<ActionWorkflow {...props} onNavigate={vi.fn()} />);
    expect(
        (
            screen.getByRole("radio", {
                name: "Roll in Gyrinx",
            }) as HTMLInputElement
        ).checked,
    ).toBe(true);
    expect((screen.getByRole("spinbutton") as HTMLInputElement).disabled).toBe(
        true,
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("roll_mode")).toBe("roll");
    expect(body.has("rolled")).toBe(false);
    expect(body.get("command_key")).toBe("command-one");
    expect(document.querySelector("form form")).toBeNull();
});

test("lost responses retain readable entered rolls immediately and exact retry values", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("lost"))
        .mockResolvedValueOnce(
            json({ saved: true, facts: saved, nextUrl: "/choose/" }),
        );
    vi.stubGlobal("fetch", fetch);
    render(<ActionWorkflow {...props} onNavigate={vi.fn()} />);
    await userEvent.click(
        screen.getByRole("radio", { name: "Record my roll" }),
    );
    await userEvent.type(screen.getByRole("spinbutton"), "10");
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText(/Record 10 on 2D6/)).toBeTruthy();
    expect((screen.getByRole("spinbutton") as HTMLInputElement).disabled).toBe(
        true,
    );
    const stored = new URLSearchParams(
        sessionStorage.getItem(props.recoveryKey)!,
    );
    expect(stored.get("rolled")).toBe("10");
    expect(stored.has("csrfmiddlewaretoken")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[0][1].body.toString()).toBe(
        fetch.mock.calls[1][1].body.toString(),
    );
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
});

test("reload at a different stage retries the earlier command with fresh CSRF", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams({
            ...props.values,
            rolled: "11",
            roll_mode: "record",
            submitted_summary: "Mara: Record 11 on 2D6",
        }).toString(),
    );
    const fetch = vi.fn().mockResolvedValue(
        json({
            saved: true,
            replayed: true,
            nextUrl: "/current/",
            facts: saved,
        }),
    );
    vi.stubGlobal("fetch", fetch);
    render(
        <ActionWorkflow
            {...props}
            values={{ ...props.values, target_step: "review", revision: "9" }}
            csrfToken="rotated"
            fields={["review"]}
            facts={{ ...props.facts, stage: "review", roll: null }}
            onNavigate={vi.fn()}
        />,
    );
    expect(screen.getByText("Mara: Record 11 on 2D6")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("target_step")).toBe("roll");
    expect(body.get("revision")).toBe("1");
    expect(body.get("rolled")).toBe("11");
    expect(body.get("csrfmiddlewaretoken")).toBe("rotated");
    expect(screen.getByText("Earlier action confirmed")).toBeTruthy();
    expect(screen.getByText("Recorded result: Dodge")).toBeTruthy();
    expect(
        screen
            .getByRole("link", { name: "Review current flow" })
            .getAttribute("href"),
    ).toBe("/current/");
});

test("a carried roll posts the selected family without a mode or total", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValue(
            json({ saved: true, facts: saved, nextUrl: "/skill/" }),
        );
    vi.stubGlobal("fetch", fetch);
    render(
        <ActionWorkflow
            {...props}
            values={{ ...props.values, skill_set_id: "power" }}
            facts={{
                ...props.facts,
                stage: "skill",
                skill_random: true,
                skillRoll: {
                    ...props.facts.roll!,
                    choices: {
                        legend: "Select a power family",
                        name: "skill_set_id",
                        value: "power",
                        errors: [],
                        options: [
                            {
                                value: "power",
                                label: "Biomancy",
                                carried:
                                    "Your D6 roll of 2 carries over to this power family.",
                            },
                        ],
                    },
                },
            }}
            onNavigate={vi.fn()}
        />,
    );
    expect(screen.queryByRole("spinbutton")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("skill_set_id")).toBe("power");
    expect(body.has("rolled")).toBe(false);
    expect(body.has("roll_mode")).toBe(false);
});

test("decline promotion captures only the initiating busy control and exact intent", async () => {
    let finish!: (value: unknown) => void;
    const fetch = vi
        .fn()
        .mockReturnValue(new Promise((resolve) => (finish = resolve)));
    vi.stubGlobal("fetch", fetch);
    render(
        <ActionWorkflow
            {...props}
            facts={{
                ...props.facts,
                stage: "advancement",
                decline_promotion: true,
                roll: null,
                advancements: [
                    {
                        key: "promote",
                        name: "Specialist",
                        minimum: null,
                        rating: 10,
                        forcedRandom: false,
                    },
                ],
            }}
            onNavigate={vi.fn()}
        />,
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Keep current rank and roll 2D6" }),
    );
    expect(
        screen
            .getByRole("button", { name: "Keep current rank and roll 2D6" })
            .getAttribute("data-busy"),
    ).toBe("on");
    expect(
        screen
            .getByRole("button", { name: "Continue" })
            .hasAttribute("data-busy"),
    ).toBe(false);
    expect(
        (fetch.mock.calls[0][1].body as URLSearchParams).get(
            "decline_promotion",
        ),
    ).toBe("1");
    finish(json({ saved: true, facts: saved, nextUrl: "/choose/" }));
});

test("passive drafts remain scoped to the exact stage and correction pick", async () => {
    const view = render(<ActionWorkflow {...props} />);
    await userEvent.click(
        screen.getByRole("radio", { name: "Record my roll" }),
    );
    fireEvent.change(screen.getByRole("spinbutton"), {
        target: { value: "8" },
    });
    view.unmount();
    const other = render(
        <ActionWorkflow {...props} draftKey="draft:other:skill:pick-a" />,
    );
    expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe("");
    other.unmount();
    render(<ActionWorkflow {...props} />);
    expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe(
        "8",
    );
});

test("authored review lines retain their line breaks", () => {
    render(
        <ActionWorkflow
            {...props}
            facts={{
                ...props.facts,
                stage: "review",
                roll: null,
                reviewChoice: {
                    label: "Selection",
                    title: "Tier 2",
                    description: "First effect.\nSecond effect.",
                    meta: "Rating +20¢",
                },
            }}
        />,
    );
    expect(screen.getByText(/First effect/).textContent).toBe(
        "First effect.\nSecond effect.",
    );
    expect(screen.getByText(/First effect/).className).toContain(
        "whitespace-pre-line",
    );
});

test("known rejected drafts from another stage do not replace the current stage", () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams({
            ...props.values,
            target_step: "skill",
            draft_key: "draft:other:skill",
            rolled: "4",
            __workflow_rejected: "1",
        }).toString(),
    );
    render(<ActionWorkflow {...props} />);
    expect(screen.queryByRole("button", { name: "Retry save" })).toBeNull();
    expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe("");
    expect(sessionStorage.getItem("draft:other:skill")).toContain("4");
});

test("an older passive draft requires explicit review before another write", async () => {
    sessionStorage.setItem(
        props.draftKey,
        JSON.stringify({
            revision: "0",
            values: { roll_mode: "record", rolled: "8" },
            summary: "Mara: earlier total8",
        }),
    );
    const navigate = vi.fn();
    render(<ActionWorkflow {...props} onNavigate={navigate} />);
    expect(screen.getByText("Mara: earlier total8")).toBeTruthy();
    expect((screen.getByRole("spinbutton") as HTMLInputElement).disabled).toBe(
        true,
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Review current flow" }),
    );
    expect(navigate).toHaveBeenCalledWith(props.action);
    expect(sessionStorage.getItem(props.draftKey)).toBeNull();
});

test("malformed success facts retain the original command for retry", async () => {
    const fetch = vi.fn().mockResolvedValue(
        json({
            saved: true,
            replayed: true,
            nextUrl: "/current/",
            facts: null,
        }),
    );
    vi.stubGlobal("fetch", fetch);
    render(<ActionWorkflow {...props} onNavigate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByRole("button", { name: "Retry save" })).toBeTruthy();
    expect(sessionStorage.getItem(props.recoveryKey)).toBeTruthy();
});

test("ordinary refresh uses the owned recovery URL after a lost response", async () => {
    const fetch = vi.fn().mockImplementation(() => {
        expect(window.location.pathname + window.location.search).toBe(
            props.recoveryHref,
        );
        return Promise.reject(new Error("lost"));
    });
    vi.stubGlobal("fetch", fetch);
    const first = render(<ActionWorkflow {...props} onNavigate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    first.unmount();
    render(
        <ActionWorkflow
            {...props}
            fields={[]}
            hiddenFields={[]}
            facts={{
                ...props.facts,
                stage: "unavailable",
                recovery_only: true,
                roll: null,
            }}
            onNavigate={vi.fn()}
        />,
    );
    expect(screen.getByRole("button", { name: "Retry save" })).toBeTruthy();
    expect(sessionStorage.getItem(props.recoveryKey)).toBeTruthy();
});

test("a key refusal cannot discard an earlier uncertain command", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("lost"))
        .mockResolvedValueOnce(
            json(
                {
                    code: "key_conflict",
                    errors: { __all__: ["Different submitted values."] },
                },
                409,
            ),
        );
    vi.stubGlobal("fetch", fetch);
    render(<ActionWorkflow {...props} onNavigate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const retained = sessionStorage.getItem(props.recoveryKey);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(
        screen.queryByRole("button", { name: "Review current flow" }),
    ).toBeNull();
    expect(screen.getByRole("button", { name: "Retry save" })).toBeTruthy();
    expect(sessionStorage.getItem(props.recoveryKey)).toBe(retained);
    expect(
        (
            screen.getByRole("radio", {
                name: "Roll in Gyrinx",
            }) as HTMLInputElement
        ).disabled,
    ).toBe(true);
});

test("confirming another stage's command preserves the current passive draft", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams({
            ...props.values,
            submitted_summary: "Earlier roll",
        }).toString(),
    );
    const currentKey = "draft:other:skill";
    const currentDraft = JSON.stringify({
        revision: "1",
        values: { skill_id: "Dodge" },
    });
    sessionStorage.setItem(currentKey, currentDraft);
    const fetch = vi.fn().mockResolvedValue(
        json({
            saved: true,
            replayed: true,
            facts: saved,
            nextUrl: "/earlier/",
        }),
    );
    vi.stubGlobal("fetch", fetch);
    render(
        <ActionWorkflow
            {...props}
            draftKey={currentKey}
            values={{
                ...props.values,
                draft_key: currentKey,
                target_step: "skill",
            }}
            onNavigate={vi.fn()}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(sessionStorage.getItem(currentKey)).toBe(currentDraft);
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
});

test("review of an earlier stage conflict preserves the current passive draft", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams({
            ...props.values,
            submitted_summary: "Earlier roll",
        }).toString(),
    );
    const currentKey = "draft:other:skill";
    const currentDraft = JSON.stringify({
        revision: "1",
        values: { skill_id: "Dodge" },
    });
    sessionStorage.setItem(currentKey, currentDraft);
    const fetch = vi.fn().mockResolvedValue(
        json(
            {
                code: "revision_conflict",
                errors: { __all__: ["The earlier flow changed."] },
                reviewUrl: "/earlier/current/",
            },
            409,
        ),
    );
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(
        <ActionWorkflow
            {...props}
            draftKey={currentKey}
            values={{
                ...props.values,
                draft_key: currentKey,
                target_step: "skill",
            }}
            onNavigate={navigate}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    await userEvent.click(
        screen.getByRole("button", { name: "Review current flow" }),
    );
    expect(navigate).toHaveBeenCalledWith("/earlier/current/");
    expect(sessionStorage.getItem(currentKey)).toBe(currentDraft);
});

test("tier details remain inside the radio label and empty errors do not change spacing", async () => {
    render(
        <ActionWorkflow
            {...props}
            facts={{
                ...props.facts,
                stage: "choose",
                roll: null,
                back_href: "/back/",
                back_label: "← Back",
                cancel_href: "/cancel/",
                items: [
                    {
                        key: "rig|tier",
                        name: "Hunting rig",
                        current: "None",
                        tier: "Tier1",
                        effect: "Improve S by1",
                        before: 0,
                        after: 20,
                    },
                ],
            }}
        />,
    );
    const detail = screen.getByText("Model rating 0¢ → 20¢");
    expect(detail.closest("label")).toBeTruthy();
    expect(detail.parentElement?.className).toContain("border-t");
    await userEvent.click(detail);
    expect(
        (screen.getByRole("radio", { name: /Tier1/ }) as HTMLInputElement)
            .checked,
    ).toBe(true);
    const section = screen
        .getByRole("heading", { name: "Choose tier" })
        .closest("section")!;
    expect(section.lastElementChild?.firstElementChild?.tagName).toBe(
        "FIELDSET",
    );
    expect(screen.getByRole("link", { name: "← Back" }).className).toContain(
        "mr-auto",
    );
    expect(screen.getByRole("link", { name: "Cancel" }).className).toContain(
        "text-red-600!",
    );
});

const gapFacts = {
    ...saved,
    selection: "Random skill or power",
    rolls: [3, 6, 1].map((roll) => ({ roll, dice: "d6" })),
    attempts: [
        { roll: 3, result_name: null },
        { roll: 6, result_name: null },
        { roll: 1, result_name: "QA First whisper" },
    ],
};
const randomSkillProps: ActionWorkflowProps = {
    ...props,
    facts: {
        ...props.facts,
        stage: "skill",
        roll: null,
        skill_random: true,
        skillRoll: {
            ...props.facts.roll!,
            dice: "D6",
            minimum: 1,
            maximum: 6,
            choices: {
                legend: "Select a power family",
                name: "skill_set_id",
                value: "whispers",
                errors: [],
                options: [
                    { value: "whispers", label: "QA Whispers", carried: "" },
                ],
            },
        },
    },
    values: {
        ...props.values,
        draft_key: "draft:record:skill",
        target_step: "skill",
        skill_set_id: "whispers",
    },
    fields: ["request_key", "roll_mode", "rolled", "skill_set_id"],
    hiddenFields: ["request_key"],
    action: "/flow/skill/",
    draftKey: "draft:record:skill",
    recoveryHref: "/flow/skill/?recover=1&gang_id=gang",
};

test("a successful random power draw accepts empty faces before its named result", async () => {
    const fetch = vi.fn().mockResolvedValue(
        json({
            saved: true,
            replayed: false,
            facts: gapFacts,
            nextUrl: "/flow/skill/",
        }),
    );
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(<ActionWorkflow {...randomSkillProps} onNavigate={navigate} />);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(navigate).toHaveBeenCalledWith("/flow/skill/");
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry save" })).toBeNull();
});

test("an uncertain random power draw recalls gap attempts without remaining frozen", async () => {
    const retained = new URLSearchParams({
        ...randomSkillProps.values,
        submitted_summary: "Roll D6 for QA Whispers",
    });
    retained.delete("rolled");
    sessionStorage.setItem(props.recoveryKey, retained.toString());
    const fetch = vi.fn().mockResolvedValue(
        json({
            saved: true,
            replayed: true,
            facts: gapFacts,
            nextUrl: "/flow/skill/",
        }),
    );
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(
        <ActionWorkflow
            {...randomSkillProps}
            csrfToken="rotated-token"
            onNavigate={navigate}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const expected = new URLSearchParams(retained);
    expected.set("csrfmiddlewaretoken", "rotated-token");
    expect((fetch.mock.calls[0][1].body as URLSearchParams).toString()).toBe(
        expected.toString(),
    );
    expect(screen.getByText("Earlier action confirmed")).toBeTruthy();
    expect(screen.getByText("Recorded result: QA First whisper")).toBeTruthy();
    expect(screen.getAllByText(/^Recorded result:/)).toHaveLength(1);
    expect(
        screen
            .getByRole("link", { name: "Review current flow" })
            .getAttribute("href"),
    ).toBe("/flow/skill/");
    expect(screen.queryByRole("button", { name: "Retry save" })).toBeNull();
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
});

test.each([17, false, { name: "QA First whisper" }, ["QA First whisper"]])(
    "a malformed attempt name %j keeps the command available for retry",
    async (result_name) => {
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(
                json({
                    saved: true,
                    replayed: true,
                    facts: { ...gapFacts, attempts: [{ result_name }] },
                    nextUrl: "/flow/skill/",
                }),
            ),
        );
        const navigate = vi.fn();
        render(<ActionWorkflow {...randomSkillProps} onNavigate={navigate} />);
        await userEvent.click(screen.getByRole("button", { name: "Continue" }));
        expect(screen.getByRole("button", { name: "Retry save" })).toBeTruthy();
        expect(sessionStorage.getItem(props.recoveryKey)).toBeTruthy();
        expect(navigate).not.toHaveBeenCalled();
    },
);

const reviewProps: ActionWorkflowProps = {
    ...props,
    facts: {
        ...props.facts,
        stage: "review",
        roll: null,
        submit_label: "Confirm",
    },
    values: {
        ...props.values,
        draft_key: "draft:record:review",
        target_step: "review",
        review: "review-before-payment-change",
    },
    fields: ["review"],
    hiddenFields: ["review"],
    action: "/flow/review/",
    draftKey: "draft:record:review",
    recoveryHref: "/flow/review/?recover=1&gang_id=gang",
};
const refreshedReview: ActionWorkflowProps = {
    ...reviewProps,
    values: {
        ...reviewProps.values,
        command_key: "command-after-payment-change",
        review: "review-after-payment-change",
    },
    csrfToken: "rotated-review-csrf",
};

test("a rejected review reload confirms fresh payment facts with a fresh command identity", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(
            json({ errors: { review: ["Review the changed payment."] } }, 422),
        )
        .mockResolvedValueOnce(
            json({ saved: true, facts: saved, nextUrl: "/done/" }),
        );
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    const view = render(
        <ActionWorkflow {...reviewProps} onNavigate={navigate} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await userEvent.click(screen.getByRole("button", { name: "Reload" }));
    expect(navigate).toHaveBeenCalledWith(reviewProps.recoveryHref);
    const retained = new URLSearchParams(
        sessionStorage.getItem(props.recoveryKey)!,
    );
    expect(retained.get("__workflow_rejected")).toBe("1");
    view.unmount();
    render(<ActionWorkflow {...refreshedReview} onNavigate={navigate} />);
    expect(screen.queryByRole("button", { name: "Retry save" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    const body = fetch.mock.calls[1][1].body as URLSearchParams;
    expect(body.get("review")).toBe(refreshedReview.values.review);
    expect(body.get("command_key")).toBe(refreshedReview.values.command_key);
    expect(body.get("revision")).toBe(reviewProps.values.revision);
    expect(body.get("csrfmiddlewaretoken")).toBe(refreshedReview.csrfToken);
    expect(navigate).toHaveBeenLastCalledWith("/done/");
});

test("a passive same-revision review draft uses the current signed review", async () => {
    sessionStorage.setItem(
        reviewProps.draftKey,
        JSON.stringify({
            revision: reviewProps.values.revision,
            values: { review: reviewProps.values.review },
        }),
    );
    const fetch = vi
        .fn()
        .mockResolvedValue(
            json({ saved: true, facts: saved, nextUrl: "/done/" }),
        );
    vi.stubGlobal("fetch", fetch);
    render(<ActionWorkflow {...refreshedReview} onNavigate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("review")).toBe(refreshedReview.values.review);
    expect(body.get("command_key")).toBe(refreshedReview.values.command_key);
});

test("an unknown review reload preserves the exact original token and command identity", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("lost after send"))
        .mockResolvedValueOnce(
            json({
                saved: true,
                replayed: true,
                facts: saved,
                nextUrl: "/done/",
            }),
        );
    vi.stubGlobal("fetch", fetch);
    const view = render(
        <ActionWorkflow {...reviewProps} onNavigate={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    const original = new URLSearchParams(fetch.mock.calls[0][1].body);
    original.delete("csrfmiddlewaretoken");
    const retained = sessionStorage.getItem(props.recoveryKey);
    view.unmount();
    render(<ActionWorkflow {...refreshedReview} onNavigate={vi.fn()} />);
    expect(sessionStorage.getItem(props.recoveryKey)).toBe(retained);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const retry = new URLSearchParams(fetch.mock.calls[1][1].body);
    expect(retry.get("csrfmiddlewaretoken")).toBe(refreshedReview.csrfToken);
    retry.delete("csrfmiddlewaretoken");
    expect(retry.toString()).toBe(original.toString());
    expect(retry.get("review")).toBe(reviewProps.values.review);
    expect(retry.get("command_key")).toBe(reviewProps.values.command_key);
    expect(screen.getByText("Earlier action confirmed")).toBeTruthy();
});

test("a resolved random skill shows one result to review before its collapsed roll history", async () => {
    render(
        <ActionWorkflow
            {...randomSkillProps}
            facts={{
                ...randomSkillProps.facts,
                skill_title: "Random skill result",
                skill_description:
                    "The recorded D6 rolls determined this result.",
                skill_confirmation:
                    "Review this selection, then confirm it to add it to Mara.",
                skill_selected_group: "Agility",
                skill_resolved: true,
                skill_selected: "Dodge",
                submit_label: "Review result",
                skillRoll: null,
                attempts: [
                    {
                        roll: 1,
                        result_name: "Catfall",
                        is_available: false,
                        unavailable_reason: "No available skill was rolled.",
                    },
                    {
                        roll: 2,
                        result_name: "Dodge",
                        is_available: true,
                        unavailable_reason: null,
                    },
                ],
            }}
        />,
    );
    expect(
        screen.getByRole("heading", { name: "Random skill result" }),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Dodge" })).toBeTruthy();
    expect(screen.getByText("Ready to review")).toBeTruthy();
    expect(screen.getByText("Agility")).toBeTruthy();
    expect(screen.getByText(/confirm it to add it to Mara/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Review result" })).toBeTruthy();
    const summary = screen.getByText("Recorded rolls (2)");
    const history = summary.closest("details")!;
    expect(history.open).toBe(false);
    await userEvent.click(summary);
    expect(history.open).toBe(true);
    expect(screen.getByText("Catfall", { exact: false })).toBeTruthy();
    expect(screen.queryByRole("radio")).toBeNull();
});

test("a manual power choice explains confirmation and submits only the selected result", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValue(
            json({ saved: true, facts: saved, nextUrl: "/review/" }),
        );
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(
        <ActionWorkflow
            {...props}
            onNavigate={navigate}
            facts={{
                ...props.facts,
                stage: "skill",
                roll: null,
                skill_title: "Select a skill or power",
                skill_description: "Select one result across all groups.",
                skill_confirmation:
                    "Review this selection, then confirm it to add it to Mara.",
                submit_label: "Review selection",
                skillGroups: [
                    {
                        key: "agility",
                        name: "Skills: Agility",
                        skills: [{ key: "dodge", name: "Dodge" }],
                    },
                    {
                        key: "whispers",
                        name: "Powers: Whispers",
                        skills: [{ key: "whisper", name: "Second whisper" }],
                    },
                ],
            }}
            values={{ ...props.values, skill_id: "", target_step: "skill" }}
            fields={["skill_id"]}
            hiddenFields={[]}
        />,
    );
    expect(
        screen.getByText("Select one result across all groups."),
    ).toBeTruthy();
    expect(screen.getByText(/confirm it to add it to Mara/)).toBeTruthy();
    expect(screen.getByRole("group", { name: "Skills: Agility" })).toBeTruthy();
    expect(
        screen.getByRole("group", { name: "Powers: Whispers" }),
    ).toBeTruthy();
    await userEvent.click(
        screen.getByRole("radio", { name: "Second whisper" }),
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Review selection" }),
    );
    expect(fetch.mock.calls[0][1].body.get("skill_id")).toBe("whisper");
    expect(navigate).toHaveBeenCalledWith("/review/");
});

test("unavailable empty power faces remain in history while the next roll stays available", async () => {
    render(
        <ActionWorkflow
            {...randomSkillProps}
            facts={{
                ...randomSkillProps.facts,
                skill_title: "Roll for a power",
                skill_description:
                    "A D6 roll determines the power from your selected power family.",
                attempts: [
                    {
                        roll: 3,
                        result_name: null,
                        is_available: false,
                        unavailable_reason:
                            "No power has D6 result 3 in Whispers.",
                    },
                ],
            }}
        />,
    );
    expect(screen.getByRole("button", { name: "Continue" })).toBeTruthy();
    expect(screen.queryByText("Ready to review")).toBeNull();
    const summary = screen.getByText("Recorded rolls (1)");
    await userEvent.click(summary);
    expect(
        screen.getByText("No power has D6 result 3 in Whispers."),
    ).toBeTruthy();
});
