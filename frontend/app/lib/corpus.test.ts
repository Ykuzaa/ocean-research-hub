import { afterEach, describe, expect, it, vi } from "vitest";
import { getCorpusClaim, getCorpusPaper, listCorpusPapers } from "./api";

afterEach(() => vi.restoreAllMocks());

describe("staging corpus API client", () => {
  it("sends real extraction and audit filters to the staging endpoint", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ papers: [], total: 0 }), { status: 200 }),
    );
    await listCorpusPapers({ q: "ocean", extractionState: "READY_FOR_AUDIT", auditState: "NOT_VERIFIED" });
    const url = String(fetch.mock.calls[0][0]);
    expect(url).toContain("/api/corpus/papers?");
    expect(url).toContain("extraction_state=READY_FOR_AUDIT");
    expect(url).toContain("audit_state=NOT_VERIFIED");
  });

  it("uses staging paper and claim detail routes", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      new Response(JSON.stringify({ paper_id: "OAI-0001" }), { status: 200 }),
    );
    await getCorpusPaper("OAI-0001");
    await getCorpusClaim("B16-0001");
    expect(String(fetch.mock.calls[0][0])).toContain("/api/corpus/papers/OAI-0001");
    expect(String(fetch.mock.calls[1][0])).toContain("/api/corpus/claims/B16-0001");
  });
});
