/* The crop dialog on a picture input.
 *
 * Wires every <input type="file" data-crop="4:5"> to the <dialog> its
 * component renders beside it (<c-n26.picture-input>). Picking a file
 * opens the dialog: Cropper.js draws a rectangle of the declared shape
 * over the picture, opening at the largest window the picture holds,
 * dragged and resized by its handles. Confirming draws the chosen
 * window to a canvas and puts the result back on the input — so the
 * form's own save sends exactly what the dialog showed. Leaving the
 * dialog any other way clears the pick.
 *
 * Without this script — or without Cropper.js beside it — the input is
 * an ordinary file box and the server centre-crops to the same ratio
 * (n26/core/images.py). The server does that to every upload
 * regardless: the dialog picks the window, it is not trusted with the
 * rules.
 */
(function () {
    var MAX_PX = 1600;

    function wire(input) {
        var box = input.closest(".n26-picture-input");
        var dialog = box && box.querySelector("dialog[data-crop-dialog]");
        var picture = dialog && dialog.querySelector("[data-crop-image]");
        if (!picture || typeof Cropper === "undefined") return;

        var parts = (input.dataset.crop || "1:1").split(":");
        var ratio = parseFloat(parts[0]) / parseFloat(parts[1]);
        // A malformed shape declaration falls back to square rather
        // than an unconstrained rectangle nobody asked for.
        if (!isFinite(ratio) || ratio <= 0) ratio = 1;

        var confirm = dialog.querySelector("[data-crop-confirm]");
        var cancel = dialog.querySelector("[data-crop-cancel]");

        var cropper = null;
        var name = "";
        var confirmed = false;

        // With the script driving, confirming the crop is the save —
        // the form's own submit control is the scriptless path, and
        // showing both would offer the same act twice.
        if ("cropSubmit" in input.dataset && input.form) {
            var fallback = input.form.querySelector("[data-crop-fallback]");
            if (fallback) fallback.hidden = true;
        }

        function settle() {
            if (cropper) {
                cropper.destroy();
                cropper = null;
            }
            if (picture.src) {
                URL.revokeObjectURL(picture.src);
                picture.removeAttribute("src");
            }
        }

        input.addEventListener("change", function () {
            var file = input.files && input.files[0];
            if (!file || !file.type.match(/^image\//)) return;
            settle();
            name = file.name;
            confirmed = false;
            picture.src = URL.createObjectURL(file);
            dialog.showModal();
            cropper = new Cropper(picture, {
                aspectRatio: ratio,
                // The rectangle opens at the largest window the picture
                // holds, and can only be dragged and resized: the
                // picture itself never moves, zooms, or rotates, so
                // what the reader sees is the file as it is.
                viewMode: 1,
                autoCropArea: 1,
                dragMode: "none",
                zoomable: false,
                rotatable: false,
                scalable: false,
                movable: false,
                toggleDragModeOnDblclick: false,
            });
        });

        confirm.addEventListener("click", function () {
            if (!cropper) return;
            // One encoding, on confirm — dragging only ever moves the
            // rectangle, so there is no stale result to race it.
            confirm.disabled = true;
            cropper
                .getCroppedCanvas({
                    maxWidth: MAX_PX,
                    maxHeight: MAX_PX,
                    imageSmoothingQuality: "high",
                })
                .toBlob(
                    function (blob) {
                        confirm.disabled = false;
                        if (blob) {
                            var transfer = new DataTransfer();
                            var stem = name.replace(/\.[^.]+$/, "");
                            transfer.items.add(
                                new File([blob], stem + ".jpg", {
                                    type: "image/jpeg",
                                }),
                            );
                            input.files = transfer.files;
                            confirmed = true;
                        }
                        dialog.close();
                        if (
                            confirmed &&
                            "cropSubmit" in input.dataset &&
                            input.form
                        ) {
                            if (input.form.requestSubmit) {
                                input.form.requestSubmit();
                            } else {
                                input.form.submit();
                            }
                        }
                    },
                    "image/jpeg",
                    0.9,
                );
        });

        cancel.addEventListener("click", function () {
            dialog.close();
        });

        // However the dialog was left — Cancel, Esc, anything but the
        // confirm — an unconfirmed pick is cleared rather than sent
        // uncropped behind the reader's back.
        dialog.addEventListener("close", function () {
            if (!confirmed) input.value = "";
            settle();
        });
    }

    function start() {
        document
            .querySelectorAll('input[type="file"][data-crop]')
            .forEach(wire);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
