export function ownedAsset(url: string, origin: string): string;
export function sameExecutedCode(executed: string, published: string, mapped: string): string;
export function mergeBrowserCoverage(inputPaths: string[], root?: string): Promise<{
  unit: unknown;
  combined: unknown;
  additional_lines: number;
  additional_branches: number;
  browser_files: string[];
  executed_assets: {file:string;sha256:string}[];
}>;

export function mergeObservedLines(lcov:string, unit:unknown,browser:unknown,root:string):{lcov:string;additional_lines:number;additional_branches:number};
