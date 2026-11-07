import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import {
    ScenarioAuthoring,
    type ScenarioAuthoringProps,
} from "./ScenarioAuthoring";

const field = {
    name: "edit-name",
    id: "id_edit-name",
    label: "Name",
    help: "The name players see.",
    required: true,
    value: "Synthetic set",
    kind: "text",
    errors: [],
    min: null,
    max: null,
    maxLength: 200,
};
const props: ScenarioAuthoringProps = {
    csrfToken: "test-csrf",
    table: {
        name: "Synthetic set",
        purpose: "Side jobs",
        staged: true,
        archived: false,
        sideJobs: true,
    },
    tableForm: { fields: [field], errors: [] },
    addForm: null,
    entries: [
        {
            id: "entry-one",
            roll: 1,
            name: "Synthetic result",
            text: "An original description.",
            form: {
                fields: [
                    {
                        ...field,
                        name: "entry-one-text",
                        id: "id_entry-one-text",
                        label: "Description",
                        kind: "textarea",
                        value: "An original description.",
                    },
                ],
                errors: [],
            },
            image: "/synthetic.png",
            imageAlt: "Two deployment areas.",
        },
    ],
    errors: [],
    editing: "",
    complete: true,
    previewUrl: "/n26/scenario/?side_job_pick=synthetic&generate=1",
};

it("opens a labelled entry editor with the correct submitted identity", () => {
    render(<ScenarioAuthoring {...props} />);
    expect(screen.queryByLabelText("Description")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Edit entry" }));
    const description =
        screen.getByLabelText<HTMLTextAreaElement>("Description");
    expect(description.value).toBe("An original description.");
    expect(
        description
            .closest("form")
            ?.querySelector<HTMLInputElement>('input[name="entry"]')?.value,
    ).toBe("entry-one");
    expect(description.closest("form")?.enctype).toBe("multipart/form-data");
    expect(screen.getByAltText("Two deployment areas.")).toBeTruthy();
});

it("keeps a refused entry open with the submitted description and its error", () => {
    render(
        <ScenarioAuthoring
            {...props}
            editing="entry-one"
            entries={[
                {
                    ...props.entries[0],
                    form: {
                        fields: [
                            {
                                ...field,
                                label: "Description",
                                name: "entry-one-text",
                                id: "id_entry-one-text",
                                kind: "textarea",
                                value: "Unclosed *passage",
                                errors: [
                                    "Close each bold passage with an asterisk.",
                                ],
                            },
                        ],
                        errors: [],
                    },
                },
            ]}
        />,
    );
    expect(
        screen.getByLabelText<HTMLTextAreaElement>("Description").value,
    ).toBe("Unclosed *passage");
    expect(
        screen.getByText("Close each bold passage with an asterisk."),
    ).toBeTruthy();
});

it("offers restoration for a retired set and preserves the preview link", () => {
    render(
        <ScenarioAuthoring
            {...props}
            table={{ ...props.table!, archived: true }}
        />,
    );
    expect(screen.getByRole("button", { name: "Restore set" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Put live" })).toBeNull();
    expect(
        screen
            .getByRole("link", { name: "Preview in generator" })
            .getAttribute("href"),
    ).toBe(props.previewUrl);
});

it("uses the create form and reports publication errors on an incomplete table", () => {
    const { rerender } = render(
        <ScenarioAuthoring
            {...props}
            table={null}
            entries={[]}
            previewUrl=""
        />,
    );
    expect(screen.getByRole("button", { name: "Create set" })).toBeTruthy();
    expect(screen.getByLabelText<HTMLInputElement>("Name").required).toBe(true);
    rerender(
        <ScenarioAuthoring
            {...props}
            complete={false}
            previewUrl=""
            errors={[
                "Complete all six D6 entries before previewing or putting this table live.",
            ]}
        />,
    );
    expect(
        screen.queryByRole("link", { name: "Preview in generator" }),
    ).toBeNull();
    expect(
        screen.getAllByText(
            "Complete all six D6 entries before previewing or putting this table live.",
        ).length,
    ).toBeGreaterThan(0);
});
