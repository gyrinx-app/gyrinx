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
 * On a form that is the picture's own, confirming also saves, and the
 * dialog stays open until that lands: the reader watches the button
 * work, a picture the server would not take is refused in the dialog
 * on the same rectangle they can send again, and only a save that
 * landed closes it. A refusal read on a page nobody sees is a refusal
 * nobody gets.
 *
 * Without this script — or without Cropper.js beside it — the input is
 * an ordinary file box and the server centre-crops to the same ratio
 * (n26/core/images.py). The server does that to every upload
 * regardless: the dialog picks the window, it is not trusted with the
 * rules.
 */
(function () {
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

        // The stored picture's long side, stated on the input by the
        // server (n26/core/images.py). Encoding bigger than the server
        // will keep only fattens the upload; without a declared cap the
        // canvas is the crop at its natural size, and the server still
        // brings it to shape.
        var cap = parseInt(input.dataset.cropMax || "", 10);
        if (!isFinite(cap) || cap <= 0) cap = undefined;

        var confirm = dialog.querySelector("[data-crop-confirm]");
        var cancel = dialog.querySelector("[data-crop-cancel]");
        var problem = dialog.querySelector("[data-crop-error]");
        var problemText = dialog.querySelector("[data-crop-error-text]");

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

        /* The dialog while its save is in flight.
         *
         * The busy state is the design library's, set here rather than by
         * n26/busy.js: this save is a background post from a plain button,
         * which is none of the three things that script watches. Both controls
         * are shut for the duration — the save cannot be sent twice, and
         * leaving halfway would strand a post nothing is waiting for. */
        function working(on) {
            if (on) {
                confirm.setAttribute("data-busy", "on");
                confirm.setAttribute("aria-busy", "true");
            } else {
                confirm.removeAttribute("data-busy");
                confirm.removeAttribute("aria-busy");
            }
            confirm.disabled = on;
            cancel.disabled = on;
        }

        /* What the server said, at one level, from a page fetched rather than
         * drawn. Alerts state their level in data-message
         * (n26/includes/messages.html). */
        function saidAt(page, level) {
            var found = [];
            page.querySelectorAll('[data-message="' + level + '"]').forEach(
                function (alert) {
                    var said = alert.textContent.replace(/\s+/g, " ").trim();
                    if (said) found.push(said);
                },
            );
            return found;
        }

        function forget() {
            if (!problem) return;
            problem.hidden = true;
            if (problemText) problemText.textContent = "";
        }

        /* A refusal, shown where the reader is standing.
         *
         * The dialog stays open on the same rectangle, so the answer to a
         * picture the server would not take is to choose again and send
         * again. The pick stops counting as confirmed, so leaving now clears
         * it: nothing was stored, and a file left on the input would ride the
         * next save of any other field on the page. */
        function refuse(said) {
            confirmed = false;
            working(false);
            if (!problem || !problemText) return;
            problemText.textContent = said;
            problem.hidden = false;
        }

        /* Said out loud on the page the reader stays on, since the page the
         * server said it on is one nobody sees. */
        function announce(said) {
            window.dispatchEvent(
                new CustomEvent("toast", {
                    detail: { variant: "success", message: said },
                }),
            );
        }

        input.addEventListener("change", function () {
            var file = input.files && input.files[0];
            if (!file || !file.type.match(/^image\//)) return;
            settle();
            name = file.name;
            confirmed = false;
            // createObjectURL only ever mints blob: addresses; the
            // guard states that where a checker can see it, so nothing
            // file-derived reaches the src as anything else.
            var address = URL.createObjectURL(file);
            if (!address.startsWith("blob:")) return;
            picture.src = address;
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
            forget();
            working(true);
            cropper
                .getCroppedCanvas({
                    maxWidth: cap,
                    maxHeight: cap,
                    imageSmoothingQuality: "high",
                })
                .toBlob(
                    function (blob) {
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
                        // A form that is the picture's own saves from
                        // here, with the dialog still open: a refusal is
                        // read where the reader is standing, and the
                        // dialog closes on a save that landed.
                        if (
                            confirmed &&
                            "cropSubmit" in input.dataset &&
                            input.form
                        ) {
                            save(input.form);
                            return;
                        }
                        working(false);
                        dialog.close();
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
            forget();
            settle();
        });

        /* Post the picture form from the open dialog and redraw its box in
         * place, so the save does not move the reader's place on the page.
         *
         * The response is the page the plain submit would have landed on, and
         * it is read twice: for what the server said, and for the picture box
         * to put in place of this one. A page fetched in the background is the
         * only copy of those words — reading it is what marks them read — so a
         * refusal shown in the dialog and a save said in a toast are the
         * difference between an answer and silence.
         *
         * A save that landed closes the dialog before the box is swapped: the
         * dialog stands inside that box, and replacing it while open would
         * take a modal off the page without ever closing it, leaving the
         * picture it was showing held in memory.
         *
         * Anything unexpected — no marker on either side, a bad status, the
         * network — falls back to the plain submit, which is the same act with
         * a page load. A refusal the server put into words is not that: it has
         * somewhere to be read, and repeating the post would only earn it
         * again. */
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
                    if (!response.ok) throw new Error(response.status);
                    return response.text();
                })
                .then(function (html) {
                    var page = new DOMParser().parseFromString(
                        html,
                        "text/html",
                    );
                    var refused = saidAt(page, "error");
                    if (refused.length) {
                        refuse(refused.join(" "));
                        return;
                    }
                    var fresh = page.querySelector("[data-picture-box]");
                    // Saved, but the page holds no box to swap: a reload
                    // shows what landed rather than posting it again.
                    if (!fresh) {
                        window.location.reload();
                        return;
                    }
                    saidAt(page, "success").forEach(announce);
                    working(false);
                    dialog.close();
                    here.replaceWith(fresh);
                    start();
                })
                .catch(function () {
                    plain(form);
                });
        }
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
