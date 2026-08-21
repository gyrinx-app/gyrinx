/* The crop chooser on a picture input.
 *
 * Any <input type="file" data-crop="4:5"> grows a preview of that shape
 * with pan and zoom sliders when a file is picked. Every adjustment
 * redraws the chosen window onto a canvas and puts the result back on
 * the input, so what uploads is what the preview shows — the form needs
 * no script of its own and a plain submit sends the choice.
 *
 * Without this script the input is an ordinary file box and the server
 * centre-crops to the same ratio (n26/core/images.py). The server does
 * that to every upload regardless: this chooser picks the window, it is
 * not trusted with the rules.
 */
(function () {
    var MAX_PX = 1600;

    function wire(input) {
        var parts = (input.dataset.crop || "1:1").split(":");
        var ratio = parseFloat(parts[0]) / parseFloat(parts[1]);
        var ui = null;

        input.addEventListener("change", function () {
            var file = input.files && input.files[0];
            if (ui) {
                ui.root.remove();
                ui = null;
            }
            if (!file || !file.type.match(/^image\//)) return;
            var image = new Image();
            image.onload = function () {
                URL.revokeObjectURL(image.src);
                ui = build(input, image, ratio, file.name);
            };
            image.src = URL.createObjectURL(file);
        });
    }

    function build(input, image, ratio, name) {
        var root = document.createElement("div");
        root.className = "n26-crop";
        root.innerHTML =
            '<div class="n26-crop-frame"><canvas></canvas></div>' +
            '<label>Zoom <input type="range" name="" min="1" max="3" step="0.01" value="1"></label>' +
            '<label>Pan <input type="range" name="" min="0" max="1" step="0.01" value="0.5"></label>' +
            '<label>Pan down <input type="range" name="" min="0" max="1" step="0.01" value="0.5"></label>';
        input.insertAdjacentElement("afterend", root);

        var canvas = root.querySelector("canvas");
        var sliders = root.querySelectorAll('input[type="range"]');
        var zoom = sliders[0];
        var panX = sliders[1];
        var panY = sliders[2];

        // The window's base size: the largest ratio-shaped box the picture
        // holds. Zoom shrinks the window (showing less, larger); pan slides
        // whatever slack the window leaves on each axis.
        var base = Math.min(image.width, image.height * ratio);

        function window_() {
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
            var box = window_();
            var scale = Math.min(1, MAX_PX / Math.max(box.w, box.h));
            canvas.width = Math.max(1, Math.round(box.w * scale));
            canvas.height = Math.max(1, Math.round(box.h * scale));
            canvas
                .getContext("2d")
                .drawImage(
                    image,
                    box.x,
                    box.y,
                    box.w,
                    box.h,
                    0,
                    0,
                    canvas.width,
                    canvas.height,
                );
            canvas.toBlob(
                function (blob) {
                    if (!blob) return;
                    var transfer = new DataTransfer();
                    var stem = name.replace(/\.[^.]+$/, "");
                    transfer.items.add(
                        new File([blob], stem + ".jpg", { type: "image/jpeg" }),
                    );
                    input.files = transfer.files;
                },
                "image/jpeg",
                0.9,
            );
        }

        sliders.forEach(function (slider) {
            slider.addEventListener("input", redraw);
        });
        redraw();
        return { root: root };
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
