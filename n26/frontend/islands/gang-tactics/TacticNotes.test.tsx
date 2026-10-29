import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { TacticNotes } from "./TacticNotes";

const suggested = "<p><strong>Timing:</strong> Now.</p>";

/** Stands in for TinyMCE: the box's own HTML is the editor's content. */
function fakeEditor() {
    const handlers: (() => void)[] = [];
    const init = vi.fn(
        async (config: {
            target: HTMLElement;
            setup: (editor: unknown) => void;
        }) => {
            const target = config.target;
            target.setAttribute("contenteditable", "true");
            const editor = {
                getContent: () => target.innerHTML,
                setContent: (html: string) => {
                    target.innerHTML = html;
                    handlers.forEach((handler) => handler());
                },
                on: (_events: string, handler: () => void) =>
                    handlers.push(handler),
                remove: () => {},
            };
            config.setup(editor);
            return [editor];
        },
    );
    window.tinymce = { init } as never;
    return {
        init,
        type: (html: string) =>
            act(() => {
                screen.getByRole("textbox").innerHTML = html;
                handlers.forEach((handler) => handler());
            }),
    };
}

beforeEach(() => {
    delete window.tinymce;
});
afterEach(() => {
    vi.unstubAllGlobals();
    delete window.tinymce;
});

function owner(notes = "", onSaved = vi.fn()) {
    render(
        <TacticNotes
            name="Chem Queen"
            notes={notes}
            suggested={suggested}
            saveUrl="/notes/"
            csrfToken="token"
            editorScript="/tinymce.js"
            onSaved={onSaved}
        />,
    );
    return onSaved;
}

test("the editor runs with no toolbar and keeps only simple formatting", async () => {
    const { init } = fakeEditor();
    owner();
    await waitFor(() => expect(init).toHaveBeenCalled());
    const config = init.mock.calls[0][0] as unknown as Record<string, unknown>;
    expect(config.toolbar).toBe(false);
    expect(config.menubar).toBe(false);
    expect(config.inline).toBe(true);
    expect(config.valid_elements).toBe("p,br,strong/b,em/i,u,ul,ol,li");
});

test("the suggestion swaps in and own notes come back", async () => {
    const { init, type } = fakeEditor();
    owner();
    await waitFor(() => expect(init).toHaveBeenCalled());
    type("<p>Mine.</p>");
    fireEvent.click(
        screen.getByRole("button", { name: "Help me with suggested summary" }),
    );
    expect(screen.getByRole("textbox").innerHTML).toBe(suggested);
    type(`${suggested}<p>Edited.</p>`);
    fireEvent.click(screen.getByRole("button", { name: "Use my own notes" }));
    expect(screen.getByRole("textbox").innerHTML).toBe("<p>Mine.</p>");
    expect(
        screen.getByRole("button", { name: "Help me with suggested summary" }),
    ).toBeTruthy();
});

test("an empty box goes back to empty", async () => {
    const { init } = fakeEditor();
    owner();
    await waitFor(() => expect(init).toHaveBeenCalled());
    fireEvent.click(
        screen.getByRole("button", { name: "Help me with suggested summary" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Use my own notes" }));
    expect(screen.getByRole("textbox").innerHTML).toBe("");
});

test("saving sends the draft and shows what the server kept", async () => {
    const { init, type } = fakeEditor();
    const fetch = vi.fn(async () => Response.json({ notes: "<p>Kept.</p>" }));
    vi.stubGlobal("fetch", fetch);
    const onSaved = owner("<p>Old.</p>");
    await waitFor(() => expect(init).toHaveBeenCalled());
    const save = screen.getByRole("button", { name: "Save notes" });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    type('<p>Kept.<span style="color:red">!</span></p>');
    fireEvent.click(save);
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith("<p>Kept.</p>"));
    const [url, request] = fetch.mock.calls[0] as unknown as [
        string,
        RequestInit,
    ];
    expect(url).toBe("/notes/");
    expect((request.headers as Record<string, string>)["X-CSRFToken"]).toBe(
        "token",
    );
    expect(screen.getByRole("textbox").innerHTML).toBe("<p>Kept.</p>");
    expect(screen.getByRole("button", { name: "Saved" })).toBeTruthy();
});

test("a refused save says why and keeps the draft", async () => {
    const { init, type } = fakeEditor();
    vi.stubGlobal(
        "fetch",
        vi.fn(async () =>
            Response.json({ error: "Too long." }, { status: 400 }),
        ),
    );
    owner();
    await waitFor(() => expect(init).toHaveBeenCalled());
    type("<p>Draft.</p>");
    fireEvent.click(screen.getByRole("button", { name: "Save notes" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Too long.");
    expect(screen.getByRole("textbox").innerHTML).toBe("<p>Draft.</p>");
});

test("a reader sees the saved notes and the suggestion, with no editor", () => {
    render(
        <TacticNotes
            name="Chem Queen"
            notes="<p>Theirs.</p>"
            suggested={suggested}
        />,
    );
    expect(screen.getByText("Theirs.")).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save notes" })).toBeNull();
    fireEvent.click(
        screen.getByRole("button", { name: "Help me with suggested summary" }),
    );
    expect(screen.getByText("Now.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Use my own notes" }));
    expect(screen.getByText("Theirs.")).toBeTruthy();
});

test("clicks and keys inside the notes do not reach the card", async () => {
    const { init } = fakeEditor();
    const card = vi.fn();
    render(
        <div onClick={card} onKeyDown={card}>
            <TacticNotes
                name="Chem Queen"
                notes=""
                suggested={suggested}
                saveUrl="/notes/"
                editorScript="/tinymce.js"
            />
        </div>,
    );
    await waitFor(() => expect(init).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("textbox"));
    fireEvent.keyDown(screen.getByRole("textbox"), { key: " " });
    fireEvent.click(
        screen.getByRole("button", { name: "Help me with suggested summary" }),
    );
    expect(card).not.toHaveBeenCalled();
});

test("saved suggestion offers Clear notes, which empties the box", async () => {
    const { init } = fakeEditor();
    vi.stubGlobal(
        "fetch",
        vi.fn(async () => Response.json({ notes: suggested })),
    );
    owner();
    await waitFor(() => expect(init).toHaveBeenCalled());
    fireEvent.click(
        screen.getByRole("button", { name: "Help me with suggested summary" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save notes" }));
    const clear = await screen.findByRole("button", { name: "Clear notes" });
    fireEvent.click(clear);
    expect(screen.getByRole("textbox").innerHTML).toBe("");
    expect(
        (
            screen.getByRole("button", {
                name: "Save notes",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(false);
    expect(
        screen.getByRole("button", { name: "Help me with suggested summary" }),
    ).toBeTruthy();
});

test("notes that say the suggestion's words offer Clear notes on load", async () => {
    const { init } = fakeEditor();
    // Saved with other spacing and emphasis than the suggestion has, and a
    // line break between paragraphs, as the server writes them.
    owner("\n<p>Timing:   <em>Now.</em></p>\n");
    await waitFor(() => expect(init).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Clear notes" })).toBeTruthy();
});

test("edited suggestion goes back to offering the suggestion", async () => {
    const { init, type } = fakeEditor();
    owner(suggested);
    await waitFor(() => expect(init).toHaveBeenCalled());
    type(`${suggested}<p>Mine too.</p>`);
    expect(
        screen.getByRole("button", { name: "Help me with suggested summary" }),
    ).toBeTruthy();
});

test("a reader of notes that are the suggestion gets no link", () => {
    render(
        <TacticNotes
            name="Chem Queen"
            notes={suggested}
            suggested={suggested}
        />,
    );
    expect(screen.queryByRole("button")).toBeNull();
});
