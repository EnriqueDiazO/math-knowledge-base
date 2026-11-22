import {describe,expect,it} from "vitest";
import {ownedAsset,sameExecutedCode,mergeObservedLines} from "../scripts/merge-browser-coverage.mjs";

describe("browser coverage provenance",()=>{
  it("accepts only assets belonging to the tested local server",()=>{
    expect(ownedAsset("http://127.0.0.1:8766/assets/DocumentSurface-hash.js","http://127.0.0.1:8766")).toBe("DocumentSurface-hash.js");
    for(const url of ["https://example.org/assets/a.js","http://127.0.0.1:8766/assets/a%2Fb.js","http://127.0.0.1:8766/assets/a.css","http://127.0.0.1:8766/other/a.js"])expect(()=>ownedAsset(url,"http://127.0.0.1:8766")).toThrow();
  });
  it("refuses maps from another build even if their asset name matches",()=>{
    const executed="export const value = 1;";
    expect(sameExecutedCode(executed,executed,executed)).toMatch(/^[a-f0-9]{64}$/u);
    expect(()=>sameExecutedCode(executed,"export const value = 2;",executed)).toThrow(/differs/u);
    expect(()=>sameExecutedCode(executed,executed,"export const value = 2;")).toThrow(/differs/u);
  });
  it("unions observed line hits without adding minifier-only lines or branches",()=>{
    const branch={type:"if",loc:{start:{line:2,column:0},end:{line:2,column:15}},locations:[{start:{line:2,column:4},end:{line:2,column:8}}]};
    const unit={fileCoverageFor:()=>({branchMap:{0:branch}})};
    const browser={files:()=>["/project/a.ts"],fileCoverageFor:()=>({getLineCoverage:()=>({1:3,2:2,99:10}),branchMap:{7:branch,8:{...branch,type:"cond-expr"}},b:{7:[4],8:[100]}})};
    const merged=mergeObservedLines("SF:a.ts\nDA:1,0\nDA:2,1\nLF:2\nLH:1\nBRDA:2,0,0,0\nBRF:1\nBRH:0\nend_of_record\n",unit,browser,"/project");
    expect(merged.additional_lines).toBe(1);
    expect(merged.additional_branches).toBe(1);
    expect(merged.lcov).toContain("DA:1,3\nDA:2,2\nLF:2\nLH:2");
    expect(merged.lcov).toContain("BRDA:2,0,0,4\nBRF:1\nBRH:1");
    expect(merged.lcov).not.toContain("99");
  });
});
