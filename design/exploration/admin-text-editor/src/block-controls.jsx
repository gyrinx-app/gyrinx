import React, { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "./controls";
import { writeBlockClipboard } from "./clipboard";

export function ParagraphDivider({ editor, getPos, node, label }) {
    function addParagraph() {
        const position = getPos();
        if (typeof position !== "number") return;
        const after = position + node.nodeSize;
        editor
            .chain()
            .insertContentAt(
                after,
                { type: "paragraph" },
                { updateSelection: false },
            )
            .setTextSelection(after + 1)
            .unsetAllMarks()
            .focus()
            .run();
    }
    return (
        <div className="callout-add-paragraph">
            <Button
                icon={Plus}
                aria-label={label}
                title={label}
                preserveSelection
                onClick={addParagraph}
            />
        </div>
    );
}

export function useBlockCopy({ editor, getPos, label, html, text }) {
    const [copied, setCopied] = useState("");
    async function copy() {
        try {
            await writeBlockClipboard(html(), text());
            setCopied(`${label} copied. Paste it into the editor.`);
        } catch {
            const position = getPos();
            if (typeof position !== "number") return;
            editor.commands.setNodeSelection(position);
            editor.commands.focus();
            setCopied(`${label} selected. Use ⌘/Ctrl+C to copy it.`);
        }
    }
    return { copy, copied };
}
