import { mount as mountRoot } from "../../runtime/mount";
import { GalleryNav, type GalleryNavProps } from "./GalleryNav";

export function mount(element: HTMLElement, props: GalleryNavProps) {
    // Preserve the filter text and focus from before mount.
    const filter = element.querySelector<HTMLInputElement>("#component-filter");
    return mountRoot(element, GalleryNav, {
        ...props,
        query: filter?.value ?? "",
        focused: filter !== null && document.activeElement === filter,
    });
}
