import { mount as mountRoot } from "../../runtime/mount";
import { GalleryNav, type GalleryNavProps } from "./GalleryNav";

export function mount(element: HTMLElement, props: GalleryNavProps) {
    // Start from what was typed into the server-drawn filter, and keep its focus.
    const filter = element.querySelector<HTMLInputElement>("#component-filter");
    return mountRoot(element, GalleryNav, {
        ...props,
        query: filter?.value ?? "",
        focused: filter !== null && document.activeElement === filter,
    });
}
