import { mount as mountRoot } from "../../runtime/mount";
import { GalleryNav, type GalleryNavProps } from "./GalleryNav";

export function mount(element: HTMLElement, props: GalleryNavProps) {
    // Keep a filter typed, and focus, before the module loaded.
    const filter = element.querySelector<HTMLInputElement>("#component-filter");
    return mountRoot(element, GalleryNav, {
        ...props,
        query: filter?.value ?? "",
        focused: filter !== null && document.activeElement === filter,
    });
}
