import React, { lazy, Suspense, useRef, useState } from "react";
import { Camera } from "lucide-react";
import { Icon } from "./controls.jsx";

const PictureCropDialog = lazy(() => import("./picture-crop-dialog.jsx"));

export function ModelPictureUpload({ name, onSave }) {
    const input = useRef(null);
    const [file, setFile] = useState(null);
    return (
        <>
            <input
                ref={input}
                className="gang-portrait-input"
                type="file"
                accept="image/*"
                aria-label={`Choose picture for ${name}`}
                hidden
                onChange={(event) => {
                    setFile(event.target.files[0] || null);
                    event.target.value = "";
                }}
            />
            <button
                type="button"
                className="gang-portrait-placeholder"
                aria-label={`Add picture for ${name}`}
                title="Add picture"
                onClick={() => input.current.click()}
            >
                <Icon icon={Camera} size={18} />
            </button>
            {file && (
                <Suspense
                    fallback={
                        <span className="cm-sr" role="status">
                            Opening picture crop.
                        </span>
                    }
                >
                    <PictureCropDialog
                        file={file}
                        onCancel={() => setFile(null)}
                        onSave={onSave}
                    />
                </Suspense>
            )}
        </>
    );
}
