/** Links from LaTeX and pasted HTML share the same non-executable destination rule. */
import { Mark } from "@tiptap/core";
import { documentLink } from "../security/document-links";
export const AcademicLink = Mark.create({
  name: "academicLink",
  inclusive: false,
  addAttributes() {
    return { href: { default: null } };
  },
  parseHTML() {
    return [
      {
        tag: "a[href]",
        getAttrs: (element) => {
          const href = documentLink(element.getAttribute("href") || "");
          return href ? { href } : false;
        },
      },
    ];
  },
  renderHTML({ HTMLAttributes }) {
    const href = documentLink(String(HTMLAttributes.href || ""));
    return href
      ? ["a", { href, target: "_blank", rel: "noopener noreferrer" }, 0]
      : ["span", {}, 0];
  },
});
