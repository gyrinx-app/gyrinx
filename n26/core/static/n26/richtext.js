/*
 * Apply the page theme before TinyMCE initialises, and rebuild editors when it
 * changes.
 *
 * Load this script before form.media so its DOMContentLoaded listener updates
 * data-mce-conf before django-tinymce's init_tinymce.js reads it.
 */
(function () {
    "use strict";

    // Clipboard files can have a PNG filename without a MIME type. Supply it for TinyMCE's image handler while preserving other clipboard data.
    window.n26CampaignImages = function (editor) {
        editor.on(
            "paste drop",
            function (event) {
                var property =
                    event.type === "paste" ? "clipboardData" : "dataTransfer";
                var data = event[property];
                if (!data || !data.files.length) return;
                var types = {
                    png: "image/png",
                    jpg: "image/jpeg",
                    jpeg: "image/jpeg",
                    gif: "image/gif",
                    webp: "image/webp",
                    svg: "image/svg+xml",
                };
                var changed = false;
                var files = Array.from(data.files, function (file) {
                    var extension = file.name.split(".").pop().toLowerCase();
                    var type = types[extension];
                    if (
                        type &&
                        (!file.type || file.type === "application/octet-stream")
                    ) {
                        changed = true;
                        return new File([file], file.name, {
                            type: type,
                            lastModified: file.lastModified,
                        });
                    }
                    return file;
                });
                if (!changed) return;
                var replacement = new DataTransfer();
                Array.from(data.types).forEach(function (type) {
                    if (type !== "Files")
                        replacement.setData(type, data.getData(type));
                });
                files.forEach(function (file) {
                    replacement.items.add(file);
                });
                event[property] = replacement;
            },
            true,
        );
    };

    var isDark = function () {
        return document.documentElement.classList.contains("dark");
    };

    // oxide-dark styles the editor controls; dark styles the separate document in the editing area.
    var appearance = function (dark) {
        return {
            skin: dark ? "oxide-dark" : "oxide",
            content_css: dark ? "dark" : "default",
        };
    };

    var editors = function () {
        return document.querySelectorAll("textarea.tinymce[data-mce-conf]");
    };

    var withAppearance = function (el, dark) {
        var conf = JSON.parse(el.dataset.mceConf);
        Object.assign(conf, appearance(dark));
        el.dataset.mceConf = JSON.stringify(conf);
        return conf;
    };

    document.addEventListener("DOMContentLoaded", function () {
        var dark = isDark();
        editors().forEach(function (el) {
            withAppearance(el, dark);
        });
    });

    document.addEventListener("DOMContentLoaded", function () {
        var last = isDark();

        var resync = function () {
            var dark = isDark();
            if (dark === last || !window.tinymce) return;
            last = dark;

            // Changing the skin requires reinitialisation. remove() preserves content in the textarea, and get() returns the live editor instances.
            window.tinymce
                .get()
                .slice()
                .forEach(function (editor) {
                    var el = editor.getElement();
                    if (!el || !el.dataset.mceConf) return;
                    var conf = withAppearance(el, dark);
                    // django-tinymce resolves these JSON strings on first load. Preserve its resolved callbacks during reinitialisation.
                    ["setup", "images_upload_handler"].forEach(function (key) {
                        var callback = editor.options.get(key);
                        if (typeof callback === "function")
                            conf[key] = callback;
                    });
                    editor.remove();
                    window.tinymce.init(conf);
                });
        };

        new MutationObserver(resync).observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["class"],
        });
    });

    /*
     * Copy live editor content into textareas before htmx serialises the form.
     * Capture runs before htmx's submit handler; only the submitted form is
     * sent.
     */
    document.addEventListener(
        "submit",
        function () {
            if (window.tinymce) window.tinymce.triggerSave();
        },
        true,
    );

    /*
     * Preview the current editor content locally. Server-side rendering
     * applies safe_rich_text separately, so this preview does not verify
     * sanitisation.
     */
    document.addEventListener("alpine:init", function () {
        window.Alpine.data("richText", function (initial) {
            return {
                mode: "edit",
                html: initial || "",

                show: function (mode) {
                    if (mode === "preview") this.html = this.current();
                    this.mode = mode;
                },

                // $root is the element with x-data; $el can be the clicked button. Read its textarea directly if TinyMCE has not initialised.
                current: function () {
                    var el = this.$root.querySelector("textarea.tinymce");
                    if (!el) return this.html;
                    var editor = window.tinymce && window.tinymce.get(el.id);
                    return editor ? editor.getContent() : el.value;
                },
            };
        });
    });
})();
