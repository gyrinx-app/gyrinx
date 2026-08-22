/* The crop dialog on a picture input.
 *
 * Wires every <input type="file" data-crop="4:5"> to the <dialog> its
 * component renders beside it (<c-n26.picture-input>). Picking a file
 * opens the dialog: the picture shows in a window of the declared
 * shape, panned and zoomed by the sliders, and confirming draws the
 * chosen window to a canvas and puts the result back on the input — so
 * the form's own save sends exactly what the dialog showed. Leaving the
 * dialog any other way clears the pick.
 *
 * Without this script the input is an ordinary file box and the server
 * centre-crops to the same ratio (n26/core/images.py). The server does
 * that to every upload regardless: the dialog picks the window, it is
 * not trusted with the rules.
 */
(function () {
    var MAX_PX = 1600;

    function wire(input) {
        var box = input.closest(".n26-picture-input");
        var dialog = box && box.querySelector("dialog[data-crop-dialog]");
        if (!dialog) return;

        var parts = (input.dataset.crop || "1:1").split(":");
        var ratio = parseFloat(parts[0]) / parseFloat(parts[1]);
        // A malformed shape declaration falls back to square rather than
        // poisoning every window computation with NaN.
        if (!isFinite(ratio) || ratio <= 0) ratio = 1;

        var canvas = dialog.querySelector("canvas");
        var sliders = dialog.querySelectorAll('input[type="range"]');
        var zoom = sliders[0];
        var panX = sliders[1];
        var panY = sliders[2];
        var confirm = dialog.querySelector("[data-crop-confirm]");
        var cancel = dialog.querySelector("[data-crop-cancel]");

        var image = null;
        var name = "";
        var confirmed = false;

        // The window's base size: the largest ratio-shaped box the
        // picture holds. Zoom shrinks the window (showing less,
        // larger); pan slides whatever slack the window leaves on each
        // axis.
        function window_() {
            var base = Math.min(image.width, image.height * ratio);
            var w = base / parseFloat(zoom.value);
            var h = w / ratio;
            return {
                w: w,
                h: h,
                x: (image.width - w) * parseFloat(panX.value),
                y: (image.height - h) * parseFloat(panY.value),
            };
        }

        function redraw() {
            if (!image) return;
            var boxw = window_();
            var scale = Math.min(1, MAX_PX / Math.max(boxw.w, boxw.h));
            canvas.width = Math.max(1, Math.round(boxw.w * scale));
            canvas.height = Math.max(1, Math.round(boxw.h * scale));
            canvas
                .getContext("2d")
                .drawImage(
                    image,
                    boxw.x,
                    boxw.y,
                    boxw.w,
                    boxw.h,
                    0,
                    0,
                    canvas.width,
                    canvas.height,
                );
        }

        input.addEventListener("change", function () {
            var file = input.files && input.files[0];
            if (!file || !file.type.match(/^image\//)) return;
            var loading = new Image();
            loading.onload = function () {
                URL.revokeObjectURL(loading.src);
                image = loading;
                name = file.name;
                confirmed = false;
                zoom.value = 1;
                panX.value = 0.5;
                panY.value = 0.5;
                redraw();
                dialog.showModal();
            };
            // A file the browser cannot decode gets no dialog — the
            // original upload goes as picked and the server answers.
            loading.onerror = function () {
                URL.revokeObjectURL(loading.src);
            };
            loading.src = URL.createObjectURL(file);
        });

        sliders.forEach(function (slider) {
            slider.addEventListener("input", redraw);
        });

        confirm.addEventListener("click", function () {
            // One encoding, on confirm — the sliders only ever redraw
            // the preview, so there is no stale result to race it.
            confirm.disabled = true;
            canvas.toBlob(
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
