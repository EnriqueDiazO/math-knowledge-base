/** Only environments actually defined by templates_latex/notes.sty. */
import blocks from "../../../../editor/ui/document_blocks.json";
import { Node } from "@tiptap/core";
export const studyBlocks: Record<
  string,
  { label: string; arguments: number; package: string }
> = blocks;
export const SemanticBlock = Node.create({
  name: "semanticBlock",
  group: "block",
  content: "block+",
  defining: true,
  addAttributes() {
    return {
      environment: { default: "context" },
      before: { default: null },
      after: { default: null },
    };
  },
  parseHTML() {
    return [{ tag: "section[data-study-block]" }];
  },
  renderHTML({ node }) {
    return [
      "section",
      { "data-study-block": String(node.attrs.environment) },
      [
        "header",
        { contenteditable: "false" },
        studyBlocks[String(node.attrs.environment)]?.label ||
          "Bloque de estudio",
      ],
      ["div", 0],
    ];
  },
});
