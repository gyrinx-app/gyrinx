import { useEffect, useMemo, useRef, useState } from "react";

/** The part of a TinyMCE editor the notes box uses. */
type Editor = {
    getContent: () => string;
    setContent: (html: string) => void;
    on: (events: string, handler: () => void) => void;
    remove: () => void;
};
type TinyMCE = {
    init: (config: Record<string, unknown>) => Promise<Editor[]>;
};
declare global {
    interface Window {
        tinymce?: TinyMCE;
    }
}

let loading: Promise<TinyMCE> | null = null;

/** The site's TinyMCE, loaded once for every card on the page. */
function loadEditor(src: string) {
    if (window.tinymce) return Promise.resolve(window.tinymce);
    loading ??= new Promise<TinyMCE>((resolve, reject) => {
        const script = document.createElement("script");
        script.src = src;
        script.onload = () =>
            window.tinymce ? resolve(window.tinymce) : reject(new Error());
        script.onerror = () => {
            loading = null;
            reject(new Error());
        };
        document.head.append(script);
    });
    return loading;
}

/**
 * The letters of some notes, without formatting or any spacing. The editor
 * and the server's cleaner each write HTML their own way, and may or may not
 * put a line break between paragraphs, so two notes say the same thing when
 * their letters match. Parsed inertly: nothing in it loads.
 */
function wordsOf(html: string) {
    const text = new DOMParser().parseFromString(html, "text/html").body
        .textContent;
    return (text ?? "").replace(/\s+/g, "");
}

/**
 * What the editor keeps from a paste or a shortcut. The same short list
 * the server cleans to (``TACTICS_NOTES_TAGS``): emphasis, paragraphs and
 * lists, with no attributes, so nothing pasted can restyle the card.
 */
const VALID_ELEMENTS = "p,br,strong/b,em/i,u,ul,ol,li";

/**
 * A card's tactics notes: the owner's own words, and a suggested summary
 * a reader may swap in to start from.
 *
 * The owner writes in TinyMCE with no toolbar, so Ctrl or Cmd with B, I
 * and U still format and a paste keeps its emphasis. Anyone else reads
 * the saved notes. "Help me with suggested summary" puts the suggestion
 * in the box as if typed, and "Use my own notes" puts back what was there
 * before. Nothing is kept until the owner saves.
 *
 * Every piece of HTML drawn here came from the server already cleaned
 * (``clean_tactics_notes``) or escaped (``suggested_summary``), which is
 * what makes setting it as HTML safe.
 */
export function TacticNotes({
    name,
    notes,
    suggested,
    saveUrl,
    csrfToken,
    editorScript,
    onSaved,
    bonus,
}: {
    name: string;
    notes: string;
    suggested: string;
    /** Where the owner saves; absent for anyone else. */
    saveUrl?: string;
    csrfToken?: string;
    editorScript?: string;
    onSaved?: (notes: string) => void;
    /** Drawn as a bonus: said under the buttons, where the card has room. */
    bonus?: boolean;
}) {
    const editable = Boolean(saveUrl && editorScript);
    const box = useRef<HTMLDivElement>(null);
    const editor = useRef<Editor | null>(null);
    // React sets the box's HTML once; after that the editor owns it.
    const [initial] = useState(notes);
    const [saved, setSaved] = useState(notes);
    const [draft, setDraft] = useState(notes);
    const [suggesting, setSuggesting] = useState(false);
    const [ownDraft, setOwnDraft] = useState(notes);
    const [status, setStatus] = useState<"" | "saving" | "saved">("");
    const [error, setError] = useState("");

    useEffect(() => {
        if (!editable || !box.current) return;
        let disposed = false;
        loadEditor(editorScript!)
            .then((tinymce) => {
                if (disposed || !box.current) return;
                return tinymce.init({
                    target: box.current,
                    inline: true,
                    menubar: false,
                    toolbar: false,
                    statusbar: false,
                    skin: false,
                    license_key: "gpl",
                    promotion: false,
                    branding: false,
                    plugins: "lists",
                    valid_elements: VALID_ELEMENTS,
                    valid_styles: {},
                    formats: { underline: { inline: "u", exact: true } },
                    placeholder: "Your notes on this tactic",
                    setup: (made: Editor) => {
                        made.on("input change undo redo SetContent", () =>
                            setDraft(made.getContent()),
                        );
                    },
                });
            })
            .then((made) => {
                if (!made) return;
                if (disposed) made[0]?.remove();
                else editor.current = made[0] ?? null;
            })
            .catch(() => {
                if (!disposed)
                    setError(
                        "The notes box did not load. Reload the page to try again.",
                    );
            });
        return () => {
            disposed = true;
            editor.current?.remove();
            editor.current = null;
        };
    }, [editable, editorScript]);

    // What the box holds right now, even if the last keystroke has not
    // drawn yet.
    const current = () => editor.current?.getContent() ?? draft;
    const show = (html: string) => {
        setDraft(html);
        if (editor.current) editor.current.setContent(html);
    };
    // Notes that are the suggestion already have nothing to swap in, so the
    // link offers to empty the box instead.
    const suggestedWords = useMemo(() => wordsOf(suggested), [suggested]);
    const isSuggestion =
        !suggesting &&
        suggestedWords !== "" &&
        wordsOf(draft) === suggestedWords;
    const clear = () => {
        setOwnDraft("");
        show("");
        setStatus("");
    };
    const toggle = () => {
        if (suggesting) {
            show(ownDraft);
        } else {
            setOwnDraft(current());
            show(suggested);
        }
        setSuggesting(!suggesting);
        setStatus("");
    };
    const save = async () => {
        setStatus("saving");
        setError("");
        const sent = current();
        const fields = new FormData();
        fields.append("notes", sent);
        try {
            const response = await fetch(saveUrl!, {
                method: "POST",
                body: fields,
                credentials: "same-origin",
                headers: { "X-CSRFToken": csrfToken ?? "" },
            });
            const reply = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(reply.error);
            const kept = String(reply.notes ?? "");
            setSaved(kept);
            setOwnDraft(kept);
            setSuggesting(false);
            if (kept !== sent) show(kept);
            setStatus("saved");
            onSaved?.(kept);
        } catch (failure) {
            setStatus("");
            setError(
                (failure as Error).message ||
                    "Your notes were not saved. Try again.",
            );
        }
    };

    // The card behind the box selects itself on a click or a key, and the
    // carousel drags on a press. Neither should happen while writing.
    const keep = (event: { stopPropagation: () => void }) =>
        event.stopPropagation();
    const unsaved = editable && draft !== saved;
    return (
        <div
            className="n26-tactic-notes"
            onClick={keep}
            onKeyDown={keep}
            onPointerDown={keep}
        >
            {editable ? (
                <div
                    ref={box}
                    className="n26-tactic-notes-box"
                    role="textbox"
                    aria-multiline="true"
                    aria-label={`Notes on ${name}`}
                    dangerouslySetInnerHTML={{ __html: initial }}
                />
            ) : draft ? (
                <div
                    className="n26-tactic-notes-box"
                    dangerouslySetInnerHTML={{ __html: draft }}
                />
            ) : (
                <p className="n26-tactic-notes-empty">No notes yet.</p>
            )}
            {(suggested || editable) && (
                <div className="n26-tactic-notes-actions">
                    {suggested && isSuggestion
                        ? // Only the owner can empty the box; a reader is
                          // already looking at the suggestion.
                          editable && (
                              <button
                                  type="button"
                                  className="n26-tactic-notes-link"
                                  onClick={clear}
                              >
                                  Clear notes
                              </button>
                          )
                        : suggested && (
                              <button
                                  type="button"
                                  className="n26-tactic-notes-link"
                                  onClick={toggle}
                              >
                                  {suggesting
                                      ? "Use my own notes"
                                      : "Help me with suggested summary"}
                              </button>
                          )}
                    {editable && (
                        <button
                            type="button"
                            className="n26-tactic-notes-save"
                            disabled={!unsaved || status === "saving"}
                            onClick={save}
                        >
                            {status === "saving"
                                ? "Saving…"
                                : status === "saved" && !unsaved
                                  ? "Saved"
                                  : "Save notes"}
                        </button>
                    )}
                </div>
            )}
            {bonus && <p className="n26-tactic-bonus">Bonus card</p>}
            {error && (
                <p className="n26-tactic-notes-error" role="alert">
                    {error}
                </p>
            )}
        </div>
    );
}
