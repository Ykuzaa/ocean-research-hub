import { describe, expect, it } from "vitest";
import type { EvidenceField, PaperSummary, StoredPaper } from "@/app/lib/api";
import {
  pickConflict,
  pickExtractionDemo,
  tallyDatasets,
  tallyEvidence,
  tallyFamilies,
  tallyLimitations,
  tallySections,
  tallyStatuses,
  tallyYears,
} from "@/app/lib/landing";

function field(overrides: Partial<EvidenceField> = {}): EvidenceField {
  return {
    value: null,
    conflict_values: [],
    status: "NOT_REPORTED",
    provenance_type: "AUTHOR_REPORTED_FACT",
    confidence: 0,
    source: { section: null, page: null, locator: null, evidence: null, origin: null, claimed_value: null },
    sources: [],
    verified_by: null,
    verified_at: null,
    ...overrides,
  };
}

function reported(value: unknown, evidence: string | null, overrides: Partial<EvidenceField> = {}) {
  return field({
    value,
    status: "NOT_VERIFIED",
    source: { section: "3 Training", page: 7, locator: null, evidence, origin: "PRIMARY_PAPER", claimed_value: null },
    ...overrides,
  });
}

function paper(id: string, record: Record<string, unknown>): StoredPaper {
  return {
    id,
    doi: null,
    record: { paper: { title: field({ value: `Paper ${id}` }) }, ...record } as StoredPaper["record"],
    domains: [],
    created_at: "",
    updated_at: "",
  };
}

function summary(id: string, overrides: Partial<PaperSummary> = {}): PaperSummary {
  return {
    id,
    title: `Paper ${id}`,
    authors: [],
    year: 2024,
    venue: null,
    doi: null,
    architecture: [],
    headline: null,
    extracted_field_count: 3,
    domains: [],
    created_at: "",
    updated_at: "",
    ...overrides,
  } as PaperSummary;
}

describe("tallyLimitations", () => {
  const limitation = (evidence: string | null, provenance: string) =>
    reported(["compute is the bottleneck"], evidence, { provenance_type: provenance });

  it("quotes the verbatim source sentence, not the normalised value", () => {
    const papers = [paper("a", { limitations: { compute: limitation("We were limited by GPU memory.", "AUTHOR_REPORTED_LIMITATION") } })];
    const [tally] = tallyLimitations(papers, [summary("a")]);
    expect(tally.items[0].evidence).toBe("We were limited by GPU memory.");
    expect(tally.items[0].claim).toBe("compute is the bottleneck");
  });

  it("ignores a limitation with no source sentence", () => {
    const papers = [paper("a", { limitations: { compute: limitation(null, "AUTHOR_REPORTED_LIMITATION") } })];
    expect(tallyLimitations(papers, [summary("a")])).toEqual([]);
  });

  it("ignores an AI interpretation presented as an author limitation", () => {
    const papers = [paper("a", { limitations: { compute: limitation("Seems compute bound.", "AI_INTERPRETATION") } })];
    expect(tallyLimitations(papers, [summary("a")])).toEqual([]);
  });

  it("counts one paper per family and ranks by paper count", () => {
    const papers = [
      paper("a", { limitations: { compute: limitation("GPU bound.", "AUTHOR_REPORTED_LIMITATION"), data: limitation("Sparse.", "AUTHOR_REPORTED_LIMITATION") } }),
      paper("b", { limitations: { compute: limitation("Memory bound.", "AUTHOR_REPORTED_LIMITATION") } }),
    ];
    const tallies = tallyLimitations(papers, [summary("a"), summary("b")]);
    expect(tallies.map((t) => [t.key, t.papers])).toEqual([["compute", 2], ["data", 1]]);
  });
});

describe("tallyStatuses", () => {
  it("reports every state including extraction failures, worst first", () => {
    const papers = [
      paper("a", {
        training: {
          optimizer: reported("AdamW", "We use AdamW."),
          scheduler: field({ status: "EXTRACTION_ERROR" }),
          seeds: field({ status: "EXTRACTION_ERROR" }),
          epochs: field({ status: "NOT_REPORTED" }),
        },
      }),
    ];
    const statuses = tallyStatuses(papers);
    expect(statuses.map((s) => [s.status, s.fields])).toEqual([
      ["EXTRACTION_ERROR", 2],
      ["NOT_VERIFIED", 1],
      ["NOT_REPORTED", 2], // the declared epochs field, plus the untouched title
    ]);
  });
});

describe("tallyEvidence", () => {
  it("counts sourced values and human audits separately", () => {
    const papers = [
      paper("a", {
        training: {
          optimizer: reported("AdamW", "We use AdamW."),
          lr: reported("5e-5", null),
          batch: reported(8, "Batch size 8.", { status: "VERIFIED", verified_by: "auditor" }),
        },
      }),
    ];
    const { sourcedValues, humanAudited, recordFields } = tallyEvidence(papers);
    expect(sourcedValues).toBe(2);
    expect(humanAudited).toBe(1);
    expect(recordFields).toBe(4);
  });
});

describe("tallyYears / tallySections / named tallies", () => {
  it("splits each year into extracted and bibliography-only", () => {
    const years = tallyYears([
      summary("a", { year: 2024 }),
      summary("b", { year: 2024, extracted_field_count: 0 }),
      summary("c", { year: 2023 }),
      summary("d", { year: null }),
    ]);
    expect(years).toEqual([
      { year: 2023, extracted: 1, bibliographic: 0 },
      { year: 2024, extracted: 1, bibliographic: 1 },
    ]);
  });

  it("excludes bibliography fields from section coverage", () => {
    const papers = [paper("a", { data: { datasets: reported(["ERA5"], "We use ERA5.") } })];
    expect(tallySections(papers)).toEqual([{ key: "data", label: "Data", fields: 1 }]);
  });

  it("counts how many papers name each family and dataset", () => {
    const papers = [
      paper("a", { architecture: { family: reported(["FNO"], "an FNO") }, data: { datasets: reported(["ERA5", "ERA5"], "ERA5") } }),
      paper("b", { architecture: { family: reported(["FNO"], "an FNO") } }),
    ];
    expect(tallyFamilies(papers)).toEqual([{ name: "FNO", papers: 2 }]);
    // A dataset listed twice by one paper still counts that paper once.
    expect(tallyDatasets(papers)).toEqual([{ name: "ERA5", papers: 1 }]);
  });
});

describe("pickExtractionDemo", () => {
  const training = (evidence: string | null, provenance = "AUTHOR_REPORTED_FACT") => ({
    optimizer: reported("AdamW", evidence, { provenance_type: provenance }),
    learning_rate: reported("5e-5", evidence, { provenance_type: provenance }),
    batch_size: reported(1, evidence, { provenance_type: provenance }),
  });

  it("needs three author-reported fields that each carry a source sentence", () => {
    const papers = [paper("a", { training: training("We use AdamW with lr 5e-5.") })];
    expect(pickExtractionDemo(papers, [summary("a")])?.rows).toHaveLength(3);
  });

  it("returns null when the fields are not author-reported", () => {
    const papers = [paper("a", { training: training("We use AdamW.", "AI_INTERPRETATION") })];
    expect(pickExtractionDemo(papers, [summary("a")])).toBeNull();
  });

  it("returns null when the sentences are missing", () => {
    const papers = [paper("a", { training: training(null) })];
    expect(pickExtractionDemo(papers, [summary("a")])).toBeNull();
  });
});

describe("pickConflict", () => {
  const conflict = (values: unknown[]) => field({ status: "CONFLICT", conflict_values: values });

  it("prefers short, genuinely different competing values", () => {
    const papers = [
      paper("a", { training: { batch_size: conflict([2, 1]) } }),
      paper("b", { evaluation: { metrics: conflict(["a much longer piece of prose that is not a value at all", "x"]) } }),
      paper("c", { architecture: { family: conflict(["FNO", "fno"]) } }),
    ];
    const picked = pickConflict(papers, [summary("a"), summary("b"), summary("c")]);
    expect(picked?.values).toEqual(["2", "1"]);
  });

  it("returns null when no conflict qualifies", () => {
    const papers = [paper("a", { architecture: { family: conflict(["FNO", "FNO"]) } })];
    expect(pickConflict(papers, [summary("a")])).toBeNull();
  });
});
