/** Native site zoom in a test-owned Firefox profile; never touches the user's profile. */
import { firefox } from "@playwright/test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
export async function firefoxAtZoom(base, percent = 100, videoDirectory) {
  const profile = await mkdtemp(join(tmpdir(), "mathmongo-firefox-zoom-"));
  const options = {
    headless: true,
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
  };
  if (percent === 100 && videoDirectory)
    options.recordVideo = {
      dir: videoDirectory,
      size: { width: 1440, height: 1000 },
    };
  let context = await firefox.launchPersistentContext(profile, options);
  if (percent !== 100) {
    const page = await context.newPage();
    await page.goto(base);
    await context.close();
    const result = spawnSync(
      "python3",
      [
        "-c",
        `import sqlite3,sys,time
from pathlib import Path
c=sqlite3.connect(Path(sys.argv[1])/'content-prefs.sqlite')
c.execute("INSERT OR IGNORE INTO settings(name) VALUES ('browser.content.full-zoom')")
c.execute('INSERT OR IGNORE INTO groups(name) VALUES (?)',(sys.argv[2],))
s=c.execute("SELECT id FROM settings WHERE name='browser.content.full-zoom'").fetchone()[0]
g=c.execute('SELECT id FROM groups WHERE name=?',(sys.argv[2],)).fetchone()[0]
c.execute('DELETE FROM prefs WHERE groupID=? AND settingID=?',(g,s))
c.execute('INSERT INTO prefs(groupID,settingID,value,timestamp) VALUES (?,?,?,?)',(g,s,float(sys.argv[3])/100,int(time.time())))
c.commit();c.close()`,
        profile,
        new URL(base).hostname,
        String(percent),
      ],
      { encoding: "utf8" },
    );
    if (result.status !== 0)
      throw new Error(
        "Could not set test-owned Firefox zoom: " + result.stderr,
      );
    if (videoDirectory)
      options.recordVideo = {
        dir: videoDirectory,
        size: { width: 1440, height: 1000 },
      };
    context = await firefox.launchPersistentContext(profile, options);
  }
  return {
    context,
    close: async () => {
      await context.close();
      await rm(profile, { recursive: true, force: true });
    },
  };
}
