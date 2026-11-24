import { describe, expect, it } from "vitest";
import { referenceAccessDate, restoredProposal } from "../src/study/reference-draft";
describe("complete bibliographic proposal recovery",()=>{
 it("preserves a timestamp when its displayed day is unchanged and applies only an explicit correction",()=>{
  expect(referenceAccessDate("2026-11-20","2026-11-20T12:34:56Z")).toBe("2026-11-20T12:34:56Z");
  expect(referenceAccessDate("2026-11-21","2026-11-20T12:34:56Z")).toBe("2026-11-21T00:00:00Z");
  expect(referenceAccessDate("2026-11-21")).toBe("2026-11-21T00:00:00Z");
  expect(referenceAccessDate("","2026-11-20T12:34:56Z")).toBeNull();
 });
 it.each([null,3,"[]","null","{invalid",'{"authors":[null]}','{"authors":[{"family":3}]}','{"accessed_at":3}'])("rejects malformed recovered metadata without inventing a replacement for %j", value=>{
  expect(restoredProposal(value).error).toContain("borrador original se conserva");
 });
 it("retains unknown provider metadata and keeps pre-existing manual drafts valid",()=>{
  expect(restoredProposal(undefined)).toEqual({data:{},error:""});
  const data={authors:[{family:"Noether",orcid:"original"}],publisher:"Editor",provider_extension:{edition:"rare"}};
  expect(restoredProposal(JSON.stringify(data))).toEqual({data,error:""});
 });
});
