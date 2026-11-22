"""Check a genuinely unsent form draft across a theme change in real Chrome."""

import ast
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
tree = ast.parse((root / "tests/test_mathmongo_theme_apptest.py").read_text())
source = next(
    n.value
    for n in ast.walk(tree)
    if isinstance(n, ast.Constant)
    and isinstance(n.value, str)
    and 'with st.form("source_draft")' in n.value
)
with tempfile.TemporaryDirectory(prefix="mathmongo-theme-audit-") as directory:
    work = Path(directory)
    app = work / "app.py"
    app.write_text(textwrap.dedent(source))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(
        os.environ,
        PYTHONPATH=str(root),
        MONGODB_URI="mongodb://127.0.0.1:27999",
        MONGODB_DB="mathmongo_theme_audit",
    )
    env.update(
        {f"XDG_{k}_HOME": str(work / k.lower()) for k in ["DATA", "STATE", "CACHE", "CONFIG"]}
    )
    with (work / "server.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(app),
                "--server.address=127.0.0.1",
                "--server.port=" + str(port),
                "--server.headless=true",
                "--browser.gatherUsageStats=false",
            ],
            cwd=root,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            url = f"http://127.0.0.1:{port}"
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url + "/_stcore/health", timeout=0.3) as r:
                        if r.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            js = """const {chromium}=require('@playwright/test');(async()=>{const browser=await chromium.launch({executablePath:'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});try{const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(process.argv[1]);const input=page.getByRole('textbox',{name:'Name',exact:true});await input.fill('Borrador de teoría de grupos');await page.locator('button').filter({hasText:/dark|Oscuro/}).first().click();await page.waitForFunction(()=>document.getElementById('mathmongo-session-theme')?.textContent.includes('#11191D'));const draft=await input.inputValue();if(draft!=='Borrador de teoría de grupos'||errors.length)throw new Error('Theme change lost a draft or raised a browser error');console.log(JSON.stringify({draft_preserved:true,page_errors:errors.length}));}finally{await browser.close()}})().catch(e=>{console.error(e.message);process.exitCode=1})"""
            result = subprocess.run(
                ["node", "-e", js, url],
                cwd=root / "frontend/advanced-reader",
                capture_output=True,
                text=True,
                timeout=45,
            )
            if result.returncode:
                raise RuntimeError(result.stderr)
            print(result.stdout.strip())
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
