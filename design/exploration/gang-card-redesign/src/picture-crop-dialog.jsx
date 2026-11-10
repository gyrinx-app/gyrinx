import React, { useEffect, useId, useRef, useState } from "react";
import Cropper from "cropperjs";
import cropperStyles from "cropperjs/dist/cropper.css?raw";
import { Button, useModal } from "./controls.jsx";
import cotton from "./cotton.json";

export default function PictureCropDialog({ file, onCancel, onSave }) {
    const dialog = useModal();
    const stage = useRef(null),
        cropper = useRef(null),
        title = useId();
    const [ready, setReady] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
        if (file.size > 10 * 1024 * 1024) {
            setError("Choose an image smaller than 10 MB.");
            return;
        }
        const image = new Image();
        const url = URL.createObjectURL(file);
        let active = true;
        image.alt = "";
        image.onerror = () => {
            if (active)
                setError(
                    "This file could not be opened as an image. Choose another image.",
                );
        };
        image.src = url;
        stage.current.append(image);
        // Match N26's picture-input crop controls and 4:5 fighter portrait ratio.
        cropper.current = new Cropper(image, {
            aspectRatio: 4 / 5,
            viewMode: 1,
            autoCropArea: 1,
            dragMode: "none",
            zoomable: false,
            rotatable: false,
            scalable: false,
            movable: false,
            toggleDragModeOnDblclick: false,
            ready() {
                if (active) setReady(true);
            },
        });
        return () => {
            active = false;
            cropper.current?.destroy();
            cropper.current = null;
            image.onerror = null;
            image.remove();
            URL.revokeObjectURL(url);
        };
    }, [file]);

    function confirm() {
        setBusy(true);
        setError("");
        try {
            const canvas = cropper.current.getCroppedCanvas({
                maxWidth: 1600,
                maxHeight: 1600,
                imageSmoothingQuality: "high",
            });
            canvas.toBlob(
                (blob) => {
                    if (!dialog.current?.open) return;
                    if (blob) onSave(blob);
                    else {
                        setError(
                            "The picture could not be cropped. Choose another image.",
                        );
                        setBusy(false);
                    }
                },
                "image/jpeg",
                0.9,
            );
        } catch {
            setError("The picture could not be cropped. Choose another image.");
            setBusy(false);
        }
    }

    return (
        <dialog
            ref={dialog}
            className={`${cotton.pictureCrop.root} gang-picture-crop`}
            aria-labelledby={title}
            onCancel={(event) => {
                event.preventDefault();
                if (!busy) onCancel();
            }}
        >
            <style>{cropperStyles}</style>
            <div className={cotton.pictureCrop.body}>
                <h2 id={title} className={cotton.pictureCrop.title}>
                    Crop the picture
                </h2>
                <p className={cotton.pictureCrop.description}>
                    Drag the rectangle, or its corners, to choose what shows.
                </p>
                <div className="n26-crop-stage" ref={stage} />
                {error && (
                    <div className={cotton.pictureCrop.error} role="alert">
                        {error}
                    </div>
                )}
                <div className={cotton.pictureCrop.actions}>
                    <Button
                        variant="default"
                        disabled={busy}
                        onClick={onCancel}
                    >
                        Cancel
                    </Button>
                    <Button
                        variant="success"
                        disabled={!ready || busy}
                        aria-busy={busy}
                        onClick={confirm}
                    >
                        Use this crop
                    </Button>
                </div>
            </div>
        </dialog>
    );
}
