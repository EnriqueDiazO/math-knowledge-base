import { afterEach, describe, expect, it, vi } from "vitest";
import { DocumentEditor } from "../src/knowledge-map/document-editor";
import { mountMathKeyboard } from "../src/knowledge-map/keyboard";

const { dispose } = vi.hoisted(() => ({ dispose: vi.fn() }));
vi.mock('../src/knowledge-map/keyboard',()=>({mountMathKeyboard:vi.fn(()=>dispose)}));
vi.mock('../src/knowledge-map/math',()=>({
  makeMath:(value:string,editable:boolean)=>Object.assign(document.createElement('math-field'),{value,readOnly:!editable,selection:{ranges:[[0,0]],direction:'forward'}}),
  mathErrors:()=>[],
}));
afterEach(()=>{document.body.replaceChildren();vi.clearAllMocks();});

describe('wide document editor lifecycle',()=>{
  it('mounts the keyboard on its owned page, restores scroll and destroys the adapter',()=>{
    const viewport=document.createElement('section'),host=document.createElement('div');
    viewport.append(host);document.body.append(viewport);
    const editor=new DocumentEditor(host,'Una nota con $x$ y contenido.',()=>{},undefined,{keyboardContainer:viewport,viewport});
    expect(mountMathKeyboard).toHaveBeenCalledWith(viewport);
    expect(host.closest('dialog')).toBeNull();
    viewport.scrollTop=280;
    const snapshot=editor.snapshot();
    expect(snapshot.dialogScroll).toBe(280);
    const original=editor.value();
    editor.destroy();host.replaceChildren();viewport.scrollTop=0;
    const recovered=new DocumentEditor(host,original,()=>{},snapshot,{keyboardContainer:viewport,viewport});
    recovered.restoreViewport();
    expect(viewport.scrollTop).toBe(280);
    expect(recovered.value()).toBe(original);
    recovered.destroy();expect(dispose).toHaveBeenCalledTimes(2);
  });
  it('preserves unsupported original LaTeX when ordinary prose is edited on the page',()=>{
    const viewport=document.createElement('section'),host=document.createElement('div');
    viewport.append(host);document.body.append(viewport);
    const legacy=String.raw`\begin{tikzpicture}\draw (0,0) -- (1,1);\end{tikzpicture}`;
    const editor=new DocumentEditor(host,legacy+'\n\nTexto original.',()=>{},undefined,{keyboardContainer:viewport,viewport});
    editor.editor.commands.insertContentAt(editor.editor.state.doc.content.size-1,' Otra observación.');
    expect(editor.value()).toContain(legacy);
    expect(editor.value()).toContain('Otra observación.');
    editor.destroy();
  });
});
