import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect, useRef } from "react";
import { afterEach, describe, expect, it } from "vitest";
import cotton from "../../generated/cotton.json";
import { RichTextMode } from "./RichTextMode";

function Field({
    id,
    value,
    live,
}: {
    id: string;
    value: string;
    live?: string;
}) {
    const field = useRef<HTMLTextAreaElement>(null);
    useEffect(() => {
        if (live === undefined) return;
        const textarea = field.current!;
        const previous = window.tinymce;
        window.tinymce = {
            get: (asked: string) =>
                asked === textarea.id ? { getContent: () => live } : null,
        };
        return () => {
            window.tinymce = previous;
        };
    }, [live]);
    return (
        <div data-rich-text>
            <RichTextMode initial="" />
            <div data-rich-text-editor>
                <textarea
                    ref={field}
                    className="tinymce"
                    id={id}
                    defaultValue={value}
                />
            </div>
            <div data-rich-text-preview hidden>
                <p className="text-muted">Nothing to preview yet.</p>
            </div>
        </div>
    );
}

function editor(id: string) {
    return document
        .getElementById(id)!
        .closest("[data-rich-text-editor]") as HTMLElement;
}

function previewOf(id: string) {
    return editor(id).parentElement!.querySelector(
        "[data-rich-text-preview]",
    ) as HTMLElement;
}

afterEach(() => {
    delete window.tinymce;
});

describe("RichTextMode", () => {
    it("starts on Edit and leaves the textarea in the page", () => {
        render(<Field id="id_notes" value="<p>Hello</p>" />);
        expect(
            screen
                .getByRole("button", { name: "Edit" })
                .getAttribute("aria-pressed"),
        ).toBe("true");
        expect(
            screen
                .getByRole("button", { name: "Preview" })
                .getAttribute("aria-pressed"),
        ).toBe("false");
        expect(screen.getByRole("button", { name: "Edit" }).className).toBe(
            cotton.richTextMode.active,
        );
        expect(editor("id_notes").style.display).toBe("");
        expect(previewOf("id_notes").hidden).toBe(true);
        expect(document.getElementById("id_notes")).not.toBeNull();
    });

    it("previews the textarea and keeps it mounted", async () => {
        const user = userEvent.setup();
        render(<Field id="id_notes" value="<p>Hello <em>there</em></p>" />);
        await user.click(screen.getByRole("button", { name: "Preview" }));
        const preview = previewOf("id_notes");
        expect(preview.hidden).toBe(false);
        expect(preview.querySelector("em")?.textContent).toBe("there");
        expect(editor("id_notes").style.display).toBe("none");
        expect(document.getElementById("id_notes")).not.toBeNull();
        expect(
            screen
                .getByRole("button", { name: "Preview" })
                .getAttribute("aria-pressed"),
        ).toBe("true");

        await user.click(screen.getByRole("button", { name: "Edit" }));
        expect(editor("id_notes").style.display).toBe("");
        expect(preview.hidden).toBe(true);
        expect(document.getElementById("id_notes")).not.toBeNull();
    });

    it("reads TinyMCE when the editor has booted", async () => {
        const user = userEvent.setup();
        render(
            <Field
                id="id_notes"
                value="<p>Stored</p>"
                live="<p>Typed <strong>now</strong></p>"
            />,
        );
        await user.click(screen.getByRole("button", { name: "Preview" }));
        expect(previewOf("id_notes").querySelector("strong")?.textContent).toBe(
            "now",
        );
        expect(previewOf("id_notes").textContent).not.toContain("Stored");
    });

    it("shows the empty line when there is nothing to preview", async () => {
        const user = userEvent.setup();
        render(<Field id="id_notes" value="   " />);
        await user.click(screen.getByRole("button", { name: "Preview" }));
        expect(previewOf("id_notes").textContent).toContain(
            "Nothing to preview yet.",
        );
        expect(previewOf("id_notes").querySelector("p")?.className).toBe(
            "text-muted",
        );
    });

    it("uses the sanitised initial HTML when there is no textarea", async () => {
        const user = userEvent.setup();
        render(
            <div data-rich-text>
                <RichTextMode initial="<p>Saved</p>" />
                <div data-rich-text-preview hidden />
            </div>,
        );
        await user.click(screen.getByRole("button", { name: "Preview" }));
        expect(screen.getByText("Saved").tagName).toBe("P");
    });

    it("does not submit the surrounding form", async () => {
        const user = userEvent.setup();
        let submitted = 0;
        render(
            <form
                onSubmit={(event) => {
                    event.preventDefault();
                    submitted += 1;
                }}
            >
                <Field id="id_notes" value="<p>Hello</p>" />
            </form>,
        );
        screen.getByRole("button", { name: "Preview" }).focus();
        await user.keyboard("{Enter}");
        expect(submitted).toBe(0);
        expect(previewOf("id_notes").hidden).toBe(false);
    });

    it("previews one field without hiding the other", async () => {
        const user = userEvent.setup();
        render(
            <>
                <Field id="id_notes" value="<p>Notes</p>" />
                <Field id="id_lore" value="<p>Lore</p>" />
            </>,
        );
        const lore = screen.getAllByRole("button", { name: "Preview" })[1];
        await user.click(lore);
        expect(previewOf("id_lore").textContent).toContain("Lore");
        expect(previewOf("id_notes").textContent).not.toContain("Lore");
        expect(editor("id_notes").style.display).toBe("");
        expect(editor("id_lore").style.display).toBe("none");
    });
});
