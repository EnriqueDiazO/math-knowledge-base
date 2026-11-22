/** Inspect executable text, distinguishing a host comparison from a network URL. */
export function offlineInspectionText(source) {
  // MathLive 0.111.4 checks a CDN hostname to normalize its current script URL.
  // This expression is not a destination: only a string comparison and a slash.
  // Leave every other occurrence intact, so URLs and fallback requests still fail.
  return source.replace(
    /new URL\(([a-zA-Z_$][\w$]*)\)\.hostname===(["'`])cdn\.jsdelivr\.net\2&&\(\1\+=(["'`])\/\3\)/gu,
    "false /* reviewed MathLive host comparison; no network destination */",
  );
}
