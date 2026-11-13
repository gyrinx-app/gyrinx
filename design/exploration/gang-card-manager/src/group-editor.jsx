import React, { useRef, useState } from "react";
import { X } from "lucide-react";
import { Button, TextInput, useModal } from "./controls.jsx";
import { GroupColourPalette } from "./group-colour-palette.jsx";
import cotton from "./cotton.json";

export function GroupEditor({ group, onSave, onClose, onManager }) {
    const dialog = useModal(),
        form = useRef(null);
    const [name, setName] = useState(group.name);
    const [colour, setColour] = useState(group.colour);
    const changed = name.trim() !== group.name || colour !== group.colour;
    const valid = name.trim().length > 0 && name.trim().length <= 120;
    const changes = () => ({ name: name.trim(), colour });
    return (
        <dialog
            ref={dialog}
            className={`${cotton.dialog.root} cm-group-editor`}
            aria-labelledby="group-editor-title"
            onCancel={(event) => {
                event.preventDefault();
                onClose();
            }}
        >
            <header>
                <h2 id="group-editor-title" className={cotton.dialog.title}>
                    Edit group
                </h2>
                <Button
                    icon={X}
                    aria-label="Close"
                    title="Close"
                    onClick={onClose}
                />
            </header>
            <form
                ref={form}
                onSubmit={(event) => {
                    event.preventDefault();
                    if (valid) {
                        onSave(changes());
                        onClose();
                    }
                }}
            >
                <div className="cm-group-editor-fields">
                    <label htmlFor="group-editor-name">Group name</label>
                    <TextInput
                        id="group-editor-name"
                        value={name}
                        onChange={setName}
                        required
                        maxLength={120}
                        autoFocus
                    />
                    <fieldset>
                        <legend>Group colour</legend>
                        <GroupColourPalette
                            selected={[colour]}
                            onChange={setColour}
                        />
                    </fieldset>
                </div>
                <footer>
                    <a
                        href="#card-manager"
                        aria-disabled={!valid}
                        onClick={(event) => {
                            event.preventDefault();
                            if (!form.current.reportValidity() || !valid)
                                return;
                            if (changed) onSave(changes());
                            onClose();
                            onManager();
                        }}
                    >
                        {changed
                            ? "Save and open Card Manager"
                            : "Card Manager"}
                    </a>
                    <Button variant="default" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button
                        type="submit"
                        variant="success"
                        disabled={!valid || !changed}
                    >
                        Save
                    </Button>
                </footer>
            </form>
        </dialog>
    );
}
