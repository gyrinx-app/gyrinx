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
        // Wiring runs again over a region redrawn in place; an element
        // already carrying its listeners must not gain a second set.
        if (input.dataset.cropWired) return;
        input.dataset.cropWired = "1";
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
                            save(input.form);
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

    /* Post the picture form in the background and redraw its box in
     * place, so the save does not move the reader's place on the page.
     * The response is the page the plain submit would have landed on;
     * only its picture box is taken. Anything unexpected — no marker on
     * either side, a bad status, the network — falls back to the plain
     * submit, which is the same act with a page load. */
    function save(form) {
        var here = form.closest("[data-picture-box]");
        if (!here || typeof DOMParser === "undefined") {
            plain(form);
            return;
        }
        fetch(form.action, {
            method: "POST",
            body: new FormData(form),
            credentials: "same-origin",
        })
            .then(function (response) {
                // A refusal or a broken response: the plain submit
                // repeats the act and lands wherever the server says.
                if (!response.ok) throw new Error(response.status);
                return response.text();
            })
            .then(function (html) {
                var fresh = new DOMParser()
                    .parseFromString(html, "text/html")
                    .querySelector("[data-picture-box]");
                // Saved, but the page holds no box to swap: a reload
                // shows what landed rather than posting it again.
                if (!fresh) {
                    window.location.reload();
                    return;
                }
                here.replaceWith(fresh);
                start();
            })
            .catch(function () {
                plain(form);
            });
    }

    function plain(form) {
        if (form.requestSubmit) {
            form.requestSubmit();
        } else {
            form.submit();
        }
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
