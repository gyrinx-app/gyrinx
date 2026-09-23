import { useState } from "react";
import { Input } from "../../ui";

export type FileInputProps = {
    htmlName: string;
    id: string;
    accept: string;
};

export function FileInput({ htmlName, id, accept }: FileInputProps) {
    const [dragDepth, setDragDepth] = useState(0);

    return (
        <div
            onDragEnter={(event) => {
                event.preventDefault();
                setDragDepth((depth) => depth + 1);
            }}
            onDragLeave={() => setDragDepth((depth) => Math.max(0, depth - 1))}
            onDrop={() => setDragDepth(0)}
            className={`transition-[background-color,box-shadow] ${
                dragDepth > 0
                    ? "rounded-control bg-accent/5 ring-2 ring-accent"
                    : ""
            }`}
        >
            <Input
                type="file"
                name={htmlName}
                id={id}
                accept={accept || undefined}
                className="file:mr-3 file:rounded-control file:border-0 file:bg-ink-100 file:px-3 file:py-1 file:text-sm file:font-medium file:text-ink-700 dark:file:bg-ink-800 dark:file:text-ink-200"
            />
        </div>
    );
}
