/** Collect per navigation so renderer replacement cannot silently discard hits. */
import { writeFile } from "node:fs/promises";

export async function browserCoverage(page, browser, label) {
  const enabled=browser==="chrome"&&process.env.MATHMONGO_COLLECT_BROWSER_COVERAGE==="1";
  const segments=[];
  const start=()=>page.coverage.startJSCoverage({resetOnNavigation:false});
  if(enabled)await start();
  const flush=async(restart=true)=>{
    if(!enabled)return;
    segments.push(await page.coverage.stopJSCoverage());
    if(restart)await start();
  };
  return {
    goto:async url=>{await flush();return page.goto(url);},
    reload:async()=>{await flush();return page.reload();},
    finish:async passed=>{
      await flush(false);
      if(enabled)await writeFile(process.env.MATHMONGO_INDEPENDENT_EVIDENCE+"/coverage-"+label+".json",JSON.stringify({passed,origin:process.env.MATHMONGO_INDEPENDENT_URL,segments}));
    },
  };
}
