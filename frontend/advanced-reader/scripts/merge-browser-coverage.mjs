/** Merge observed browser hits using private maps, retaining the unit-test scope. */
import {readFile,writeFile,copyFile} from "node:fs/promises";
import {basename,dirname,resolve,sep} from "node:path";
import {pathToFileURL} from "node:url";
import {createHash} from "node:crypto";
import {convert} from "ast-v8-to-istanbul";
import {mergeProcessCovs} from "@bcoe/v8-coverage";
import {parseAstAsync} from "vitest/node";
import coverageLibrary from "istanbul-lib-coverage";

const hash=value=>createHash("sha256").update(value).digest("hex");
export function ownedAsset(url,origin){
  const parsed=new URL(url);
  if(parsed.origin!==origin||!parsed.pathname.startsWith('/assets/'))throw new Error("Coverage contains an unowned URL");
  const file=decodeURIComponent(parsed.pathname.slice('/assets/'.length));
  if(file!==basename(file)||!file.endsWith('.js'))throw new Error("Invalid coverage asset path");
  return file;
}
export function sameExecutedCode(executed,published,mapped){
  const digest=hash(executed);
  if(digest!==hash(published)||digest!==hash(mapped))throw new Error("Coverage build differs from the executed published code");
  return digest;
}
/** Union LCOV lines within the original executable-line set. Branches require
 * exact original AST type/location/arm matches; minifier branches are not added.
 * Statement/function totals remain those of Vitest, never inferred from a line hit.
 */
export function mergeObservedLines(lcov,unit,browser,root){
  const stats={unit:{lines:{total:0,covered:0},branches:{total:0,covered:0}},combined:{lines:{total:0,covered:0},branches:{total:0,covered:0}}};
  const records=lcov.trim().split("end_of_record").filter(record=>record.trim()).map(record=>{
    const rows=record.trim().split("\n"),sf=rows.find(row=>row.startsWith("SF:")).slice(3),file=resolve(root,sf);
    const observed=browser.files().includes(file)?browser.fileCoverageFor(file):undefined;
    const original=unit.fileCoverageFor(file),lineHits=observed?.getLineCoverage()??{};
    const identity=value=>JSON.stringify(value);
    const branches=new Map();
    if(observed)for(const [id,branch] of Object.entries(observed.branchMap)){
      branches.set(identity(branch),observed.b[id]);
    }
    let lh=0,bh=0;
    const result=rows.map(row=>{
      if(row.startsWith("DA:")){
        const [line,old]=row.slice(3).split(',').map(Number),hits=Math.max(old,lineHits[line]??0);
        stats.unit.lines.total++;stats.combined.lines.total++;
        if(old>0)stats.unit.lines.covered++;
        if(hits>0){stats.combined.lines.covered++;lh++;}
        return "DA:"+line+","+hits;
      }
      if(row.startsWith("BRDA:")){
        const [line,id,arm,old]=row.slice(5).split(','),branch=original.branchMap[id];
        const hits=Math.max(Number(old)||0,branch?(branches.get(identity(branch))?.[Number(arm)]??0):0);
        stats.unit.branches.total++;stats.combined.branches.total++;
        if(Number(old)>0)stats.unit.branches.covered++;
        if(hits>0){stats.combined.branches.covered++;bh++;}
        return ["BRDA:"+line,id,arm,hits||old].join(',');
      }
      return row;
    });
    return result.map(row=>row.startsWith("LH:")?"LH:"+lh:row.startsWith("BRH:")?"BRH:"+bh:row).join("\n")+"\nend_of_record\n";
  });
  for(const summary of [stats.unit,stats.combined])for(const metric of Object.values(summary))metric.pct=metric.total?Math.round(10000*metric.covered/metric.total)/100:100;
  return {...stats,additional_lines:stats.combined.lines.covered-stats.unit.lines.covered,additional_branches:stats.combined.branches.covered-stats.unit.branches.covered,lcov:records.join("")};
}
export async function mergeBrowserCoverage(inputPaths,root=process.cwd()){
  const coverageDir=resolve(root,"coverage"),mapRoot=resolve(coverageDir,"browser-build/assets");
  const unit=JSON.parse(await readFile(resolve(coverageDir,"coverage-final.json"),"utf8"));
  const output=coverageLibrary.createCoverageMap(unit),allowed=new Set(output.files().map(file=>resolve(file)));
  const entries=[],proof=[];
  for(const path of inputPaths){
    const data=JSON.parse(await readFile(path,"utf8"));if(!data.passed)throw new Error("Refusing coverage from a failed browser run");
    // Chromium can omit getScriptSource for a context destroyed at navigation.
    // Reuse only source actually observed for that exact URL in this same run.
    const observed=new Map();
    for(const entry of data.segments.flat())if(typeof entry.source==="string"){
      if(observed.has(entry.url)&&observed.get(entry.url)!==entry.source)throw new Error("A tested URL changed code during the browser run");
      observed.set(entry.url,entry.source);
    }
    for(const segment of data.segments)for(const entry of segment){
      if(!entry.url||!entry.url.startsWith(data.origin+"/assets/"))continue;
      const file=ownedAsset(entry.url,data.origin);
      const mapped=await readFile(resolve(mapRoot,file),"utf8"),published=await readFile(resolve(root,"dist/assets",file),"utf8");
      const executed=entry.source??observed.get(entry.url);
      if(typeof executed!=="string")throw new Error("Executed source was never observed: "+entry.url);
      const digest=sameExecutedCode(executed,published,mapped);
      entries.push({...entry,url:pathToFileURL(resolve(mapRoot,file)).href});
      proof.push({file,sha256:digest});
    }
  }
  const merged=mergeProcessCovs([{result:entries}]);
  const browser=coverageLibrary.createCoverageMap({});
  for(const entry of merged.result){
    const asset=new URL(entry.url),code=await readFile(asset,"utf8"),sourceMap=JSON.parse(await readFile(new URL(asset.href+".map"),"utf8"));
    const originalPaths=sourceMap.sources.map(source=>resolve(dirname(asset.pathname),sourceMap.sourceRoot||"",source));
    if(!originalPaths.some(path=>allowed.has(path)))continue;
    for(let i=0;i<originalPaths.length;i++)if(allowed.has(originalPaths[i])&&await readFile(originalPaths[i],"utf8")!==sourceMap.sourcesContent[i])throw new Error("Original source changed after coverage build: "+originalPaths[i]);
    const data=await convert({ast:await parseAstAsync(code),code,sourceMap,coverage:entry,wrapperLength:0});
    for(const [file,result] of Object.entries(data))if(allowed.has(resolve(file)))browser.addFileCoverage(result);
  }
  const unitLcov=await readFile(resolve(coverageDir,"lcov.info"),"utf8");
  const combined=mergeObservedLines(unitLcov,output,browser,root);
  await copyFile(resolve(coverageDir,"lcov.info"),resolve(coverageDir,"lcov-unit.info"));
  await writeFile(resolve(coverageDir,"coverage-browser.json"),JSON.stringify(browser.toJSON()));
  await writeFile(resolve(coverageDir,"lcov.info"),combined.lcov);
  const result={...combined,lcov:undefined,browser_files:browser.files().map(file=>file.startsWith(root+sep)?file.slice(root.length+1):file),executed_assets:[...new Map(proof.map(item=>[item.file,item])).values()]};
  await writeFile(resolve(coverageDir,"browser-merge.json"),JSON.stringify(result,null,2));
  return result;
}
if(process.argv[1]&&pathToFileURL(resolve(process.argv[1])).href===import.meta.url)console.log(JSON.stringify(await mergeBrowserCoverage(process.argv.slice(2))));
