/*
 * Crop picture-input uploads with Cropper.js before submitting the form.
 *
 * Confirmation replaces the selected file with the cropped JPEG. File inputs
 * marked with data-crop-submit save their form from the dialog and display
 * validation errors there.
 * Cancelling an unconfirmed crop clears the file input.
 *
 * The server still validates, resizes and centre-crops every upload in
 * n26/core/images.py, including uploads made without this script or
 * Cropper.js.
 */
(function () {
    // Both native picture inputs and React editors use the same crop behaviour.
    window.GyrinxImageCrop = {
        create: function (picture, ratio, onCrop) {
            return new Cropper(picture, {
                aspectRatio: ratio,
                viewMode: 1,
                autoCropArea: 1,
                dragMode: "none",
                zoomable: false,
                rotatable: false,
                scalable: false,
                movable: false,
                toggleDragModeOnDblclick: false,
                crop: onCrop,
                ready: onCrop,
            });
        },
    };
    function wire(input) {
        // Partial page updates can call wire again on an input that already has listeners.
        if (input.dataset.cropWired) return;
        input.dataset.cropWired = "1";
        var box = input.closest(".n26-picture-input");
        var dialog = box && box.querySelector("dialog[data-crop-dialog]");
        var picture = dialog && dialog.querySelector("[data-crop-image]");
        if (!picture || typeof Cropper === "undefined") return;

        var parts = (input.dataset.crop || "1:1").split(":");
        var ratio = parseFloat(parts[0]) / parseFloat(parts[1]);

        if (!isFinite(ratio) || ratio <= 0) ratio = 1;

        // Limit the canvas to the server's maximum stored image size to avoid uploading pixels it will discard.
        var cap = parseInt(input.dataset.cropMax || "", 10);
        if (!isFinite(cap) || cap <= 0) cap = undefined;

        var confirm = dialog.querySelector("[data-crop-confirm]");
        var cancel = dialog.querySelector("[data-crop-cancel]");
        var problem = dialog.querySelector("[data-crop-error]");
        var problemText = dialog.querySelector("[data-crop-error-text]");

        var cropper = null;
        var name = "";
        var confirmed = false;

        // The crop confirmation submits picture-only forms, so hide their fallback submit button.
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

        /*
         * This fetch bypasses busy.js. Disable both buttons until it finishes
         * to prevent repeat confirmation or clicks on Cancel.
         */
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

        /*
         * Read messages from the fetched page using the levels rendered by
         * n26/includes/messages.html.
         */
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

        /*
         * Keep the crop open for correction. Mark it unconfirmed so
         * cancellation clears a file the server has rejected.
         */
        function refuse(said) {
            confirmed = false;
            working(false);
            if (!problem || !problemText) return;
            problemText.textContent = said;
            problem.hidden = false;
        }

        /*
         * The fetched response is not displayed, so announce its success
         * messages on the current page.
         */
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
            // Keep the file preview restricted to blob URLs.
            var address = URL.createObjectURL(file);
            if (!address.startsWith("blob:")) return;
            picture.src = address;
            dialog.showModal();
            cropper = window.GyrinxImageCrop.create(picture, ratio);
        });

        confirm.addEventListener("click", function () {
            if (!cropper) return;
            // Encode only on confirmation so dragging cannot leave an outdated encoding pending.
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
                        // Keep picture-only forms open until saving succeeds so validation errors appear in the dialog.
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

        // Clear unconfirmed files on every dismissal path so a later form submission cannot upload the uncropped file.
        dialog.addEventListener("close", function () {
            if (!confirmed) input.value = "";
            forget();
            settle();
        });

        /*
         * Save and replace the picture box without navigating. Close its
         * dialog before replacement to release the cropper and object URL.
         *
         * Display validation errors in place; retrying them would repeat the
         * same rejected save. Fall back to native submission on unexpected
         * responses or network errors.
         */
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
                    // The save succeeded; reload to display it without repeating the POST.
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
