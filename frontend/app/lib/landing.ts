import {
  getLandingAggregate,
  type LandingEvidenceItem,
  type LandingField,
  type LandingNamedTally,
  type LandingPaperReference,
} from "@/app/lib/api";

/** A transport adapter. All scientific aggregation is performed by the API. */
export type LandingStatus = "ready" | "empty" | "partial" | "unavailable";

export type LimitationTally = {
  key: string;
  label: string;
  papers: number;
  items: LandingEvidenceItem[];
  drilldownPath: string;
};

export type YearBar = {
  year: number;
  extracted: number;
  bibliographic: number;
  extractedPapers: LandingPaperReference[];
  bibliographicPapers: LandingPaperReference[];
  extractedDrilldownPath: string;
  bibliographicDrilldownPath: string;
};

export type SectionTally = {
  key: string;
  label: string;
  fields: number;
  items: LandingEvidenceItem[];
  drilldownPath: string;
};

export type StatusTally = {
  status: string;
  fields: number;
  blurb: string;
  items: LandingEvidenceItem[];
  drilldownPath: string;
};

export type NamedTally = {
  key: string;
  name: string;
  papers: number;
  items: LandingEvidenceItem[];
  drilldownPath: string;
};

export type ExtractionRow = {
  label: string;
  value: string;
  status: string;
  provenance: string;
  page: number | null;
  section: string | null;
  locator: string | null;
  evidence: string;
};

export type ExtractionDemo = {
  paperId: string;
  paperTitle: string;
  rows: ExtractionRow[];
};

export type ConflictExample = {
  paperId: string;
  paperTitle: string;
  label: string;
  values: string[];
  sources: Array<{
    evidence: string;
    page: number | null;
    section: string | null;
    locator: string | null;
    claimedValue: string;
  }>;
};

export type LandingData = {
  status: LandingStatus;
  partial: { missingRecords: number; message: string | null } | null;
  totals: {
    papers: number;
    readablePapers: number;
    domains: number;
    papersWithFields: number;
    extractedFields: number;
    recordFields: number;
    sourcedValues: number;
    humanAudited: number;
  };
  statuses: StatusTally[];
  years: YearBar[];
  limitations: LimitationTally[];
  sections: SectionTally[];
  families: NamedTally[];
  datasets: NamedTally[];
  extraction: ExtractionDemo | null;
  conflict: ConflictExample | null;
  gapPreview: {
    label: "Product Preview";
    analyticsState: "NOT_COMPUTED";
    isLiveAnalytic: false;
    description: string;
  };
};

export function formatValue(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => formatValue(item)).join(" · ");
  if (value === null || value === undefined) return "—";
  return String(value);
}

function paperTitle(paper: LandingPaperReference): string {
  return paper.title || "Untitled paper";
}

function namedTally(item: LandingNamedTally): NamedTally {
  return {
    key: item.key,
    name: item.label,
    papers: item.papers,
    items: item.items,
    drilldownPath: item.drilldown_path,
  };
}

function extractionRows(fields: LandingField[]): ExtractionRow[] {
  return fields.flatMap((field) => {
    const source = field.display_source;
    if (!source?.evidence) return [];
    return [{
      label: field.label,
      value: formatValue(field.value),
      status: field.status,
      provenance: field.provenance_type ?? "UNKNOWN",
      page: source.page,
      section: source.section,
      locator: source.locator,
      evidence: source.evidence,
    }];
  });
}

const ZERO_TOTALS: LandingData["totals"] = {
  papers: 0,
  readablePapers: 0,
  domains: 0,
  papersWithFields: 0,
  extractedFields: 0,
  recordFields: 0,
  sourcedValues: 0,
  humanAudited: 0,
};

const UNAVAILABLE: LandingData = {
  status: "unavailable",
  partial: null,
  totals: ZERO_TOTALS,
  statuses: [],
  years: [],
  limitations: [],
  sections: [],
  families: [],
  datasets: [],
  extraction: null,
  conflict: null,
  gapPreview: {
    label: "Product Preview",
    analyticsState: "NOT_COMPUTED",
    isLiveAnalytic: false,
    description: "Candidate research-gap detection is not computed while the corpus API is unavailable.",
  },
};

export async function loadLandingData(): Promise<LandingData> {
  let aggregate: Awaited<ReturnType<typeof getLandingAggregate>>;
  try {
    aggregate = await getLandingAggregate();
  } catch {
    return UNAVAILABLE;
  }

  return {
    status: aggregate.state,
    partial: aggregate.state === "partial"
      ? { missingRecords: aggregate.completeness.missing_records, message: aggregate.completeness.message }
      : null,
    totals: {
      papers: aggregate.totals.papers,
      readablePapers: aggregate.totals.readable_papers,
      domains: aggregate.totals.domains,
      papersWithFields: aggregate.totals.papers_with_extracted_fields,
      extractedFields: aggregate.totals.extracted_scientific_fields,
      recordFields: aggregate.totals.scientific_record_fields,
      sourcedValues: aggregate.totals.values_with_exact_evidence,
      humanAudited: aggregate.totals.audited_fields,
    },
    statuses: aggregate.statuses.map((item) => ({
      status: item.status,
      fields: item.fields,
      blurb: item.description,
      items: item.items,
      drilldownPath: item.drilldown_path,
    })),
    years: aggregate.years.map((item) => ({
      year: item.year,
      extracted: item.papers_with_extracted_fields,
      bibliographic: item.bibliography_only,
      extractedPapers: item.extracted_papers,
      bibliographicPapers: item.bibliographic_papers,
      extractedDrilldownPath: item.extracted_drilldown_path,
      bibliographicDrilldownPath: item.bibliographic_drilldown_path,
    })),
    limitations: aggregate.limitations.map((item) => ({
      key: item.key,
      label: item.label,
      papers: item.papers,
      items: item.items,
      drilldownPath: item.drilldown_path,
    })),
    sections: aggregate.sections.map((item) => ({
      key: item.key,
      label: item.label,
      fields: item.fields,
      items: item.items,
      drilldownPath: item.drilldown_path,
    })),
    families: aggregate.architecture_families.map(namedTally),
    datasets: aggregate.datasets.map(namedTally),
    extraction: aggregate.extraction_demo
      ? {
          paperId: aggregate.extraction_demo.paper.id,
          paperTitle: paperTitle(aggregate.extraction_demo.paper),
          rows: extractionRows(aggregate.extraction_demo.fields),
        }
      : null,
    conflict: aggregate.conflict_demo
      ? {
          paperId: aggregate.conflict_demo.paper.id,
          paperTitle: paperTitle(aggregate.conflict_demo.paper),
          label: aggregate.conflict_demo.field.label,
          values: aggregate.conflict_demo.field.conflict_values.map(formatValue),
          sources: [aggregate.conflict_demo.field.source, ...aggregate.conflict_demo.field.sources]
            .filter((source) => source.evidence && source.claimed_value !== null)
            .map((source) => ({
              evidence: source.evidence as string,
              page: source.page,
              section: source.section,
              locator: source.locator,
              claimedValue: formatValue(source.claimed_value),
            })),
        }
      : null,
    gapPreview: {
      label: aggregate.gap_preview.label,
      analyticsState: aggregate.gap_preview.analytics_state,
      isLiveAnalytic: aggregate.gap_preview.is_live_analytic,
      description: aggregate.gap_preview.description,
    },
  };
}
