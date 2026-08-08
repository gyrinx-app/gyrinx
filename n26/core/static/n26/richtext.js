/* Make TinyMCE follow the page's light/dark mode.
 *
 * The skin is baked in when an editor initialises, so this has two jobs: get the
 * right one in before the first init, and swap it when the mode changes.
 *
 * Getting in first is a matter of load order rather than cleverness. The widget
 * renders a <textarea class="tinymce" data-mce-conf="{...}">, and django-tinymce's
 * own init_tinymce.js reads that attribute on DOMContentLoaded. This file is
 * loaded *before* form.media, so its listener is registered first and runs first
 * — early enough to edit the config the library is about to read. Patching after
 * the fact would mean initialising in the wrong skin and flashing.
 */
(function () {
    "use strict";

    var isDark = function () {
        return document.documentElement.classList.contains("dark");
    };

    // oxide-dark is the editor chrome; "dark" is the stylesheet inside the
    // editable area, which is a separate document and inherits nothing.
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

    // Runs before django-tinymce's initialiser, so the first paint is already
    // in the right skin.
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

            // A skin cannot be changed on a live editor, so each one is torn down and
            // rebuilt. remove() writes the content back to the textarea on its way
            // out, which is what the re-init then picks up — no manual save needed.
            //
            // get() with no argument, not the `editors` array: TinyMCE 7 dropped that
            // property, and reading .slice() off undefined threw here silently.
            window.tinymce
                .get()
                .slice()
                .forEach(function (editor) {
                    var el = editor.getElement();
                    if (!el || !el.dataset.mceConf) return;
                    var conf = withAppearance(el, dark);
                    editor.remove();
                    window.tinymce.init(conf);
                });
        };

        new MutationObserver(resync).observe(document.documentElement, {
            attributes: true,
            attributeFilter: ["class"],
        });
    });

    /* The edit / render toggle.
     *
     * Preview reads the editor's *live* content rather than the saved value, so it
     * reflects what you are typing — a preview of the stored value would be stale
     * the moment you touched anything.
     *
     * What it shows is therefore your own input as your own browser renders it. It
     * is not the sanitiser's output: safe_rich_text runs server-side at render
     * time, and the "Sanitising" example on this component's page shows what it
     * does to hostile markup. For ordinary editing the two agree, because TinyMCE
     * will not produce anything the allowlist rejects.
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

                // $root, not $el. Alpine resolves $el against whatever is being evaluated,
                // so called from the button's @click it is the *button* — which contains no
                // textarea, so this silently returned the initial value and the preview
                // showed stale content. $root is always the element carrying x-data.
                //
                // Falls back to the textarea when TinyMCE has not booted — without the
                // form's media the editor never initialises, and a blank preview would
                // look like a bug in the component rather than a missing include.
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
