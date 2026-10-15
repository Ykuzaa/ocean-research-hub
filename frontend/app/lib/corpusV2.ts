/**
 * Corpus v2 client: records whose every value carries the sentence it was read from.
 *
 * The backend re-locates each quote on the page it cites before the corpus is committed,
 * so a value displayed here is *sourced*. It is *audited* only when `audit_state` says a
 * person checked it — the two are never collapsed into one badge.
 */
import { API_BASE_URL, ApiError } from "./api";

export type AuditState = "UNAUDITED" | "STALE" | "ACCEPTED" | "NEEDS_FIX" | "REJECTED";

/**
 * The independent machine re-check: a second reading of the paper that checks the
 * value was read in the right context. It is never a human audit, and the API keeps
 * the two in separate fields for exactly that reason.
 */
export type RecheckState =
  | "NOT_RECHECKED" | "STALE" | "CONFIRMED" | "UNREADABLE"
  | "SUSPECT" | "SUSPECT_APPLIED" | "SUSPECT_KEPT";

export type Recheck = {
  verdict: "CONFIRMED" | "SUSPECT" | "UNREADABLE";
  reason: string | null;
  correct_reading: unknown;
  checker: string;
  checked_at: string | null;
  stale?: boolean;
  triage: { decision: "APPLIED" | "KEPT"; reason: string } | null;
};

export type RecheckProgress = {
  claims: number;
  rechecked: number;
  confirmed: number;
  flagged: number;
  corrected: number;
  flag_dismissed: number;
  outstanding: number;
  stale: number;
  not_rechecked: number;
  checkers: string[];
};

export type Verdict = {
  claim_id: string;
  decision: "ACCEPTED" | "NEEDS_FIX" | "REJECTED";
  note: string | null;
  corrected_value: unknown;
  auditor: string;
  decided_at: string;
  stale?: boolean;
};

export type Claim = {
  claim_id: string;
  slug: string;
  path: string;
  kind: "RESULT" | "TRAINING" | "TRAINING_EXTRA" | "METHOD" | "DATASET" | "LIMITATION" | "CONFLICT" | "EXCLUSION" | "OTHER";
  field: string;
  value: unknown;
  unit: string | null;
  page_pdf: number | null;
  page_printed: number | null;
  quote: string | null;
  note: string | null;
  evidence_status: string;
  context: Record<string, unknown>;
  fingerprint: string;
  paper_title: string;
  pdf: string | null;
  audit: Verdict | null;
  audit_state: AuditState;
  recheck: Recheck | null;
  recheck_state: RecheckState;
};

export type PaperAudit = { claims: number; audited: number; accepted: number } | null;

export type PaperSummaryV2 = {
  slug: string;
  title: string;
  year: number | null;
  venue: string | null;
  doi: string | null;
  domains: string[];
  excluded: string | null;
  tasks: string[];
  families: string[];
  proposed: string[];
  datasets: string[];
  experiment_count: number;
  result_count: number;
  claim_count: number;
  pdf_pages: number | null;
  audit: PaperAudit;
};

export type Evidence = { field?: string | null; page: number | null; quote: string | null };

export type TrainingValue = {
  field: string;
  value: unknown;
  unit: string | null;
  page: number | null;
  quote: string | null;
  evidence_status: string;
  note: string | null;
  extra_evidence: Array<{ claim: string | null; page: number | null; quote: string | null }>;
};

export type ResultRow = {
  metric: string | null;
  metric_raw: string | null;
  value: number | null;
  unit: string | null;
  split: string | null;
  config: string | null;
  dataset: string | null;
  baseline_name: string | null;
  baseline_value: number | null;
  higher_is_better: boolean | null;
  is_best_in_table: boolean;
  page: number | null;
  quote: string | null;
  evidence_status: string;
  note: string | null;
};

export type PaperDetailV2 = PaperSummaryV2 & {
  source: { file: string; sha256_prefix: string; pdf_pages: number; printed_page_offset?: number };
  methods: Array<{
    name: string; family: string; family_raw: string | null; role: string | null;
    is_novel_in_paper: boolean; architecture_note: string | null; evidence: Evidence[];
  }>;
  dataset_records: Array<{
    name: string; role: string | null; variables: string[];
    spatial_resolution: string | null; temporal_resolution: string | null;
    region: string | null; period: [string | null, string | null]; evidence: Evidence[];
  }>;
  experiments: Array<{
    id: string; task: string; task_raw: string | null; method: string | null; family: string | null;
    datasets: string[]; target: string | null; note: string | null;
    training: TrainingValue[]; results: ResultRow[];
  }>;
  orphan_results: ResultRow[];
  limitations: Array<{ theme: string; page: number | null; quote: string | null }>;
  conflicts: Array<{
    field: string; values: unknown[]; chosen: unknown; reason: string | null; sources: Evidence[];
  }>;
  not_reported: Array<{ field: string; searched: string[] }>;
  excluded_evidence: { reason: string; page_pdf?: number; quote?: string } | null;
  claims: Claim[];
};

export type AuditProgress = {
  claims: number;
  states: Partial<Record<AuditState, number>>;
  audited: number;
  accepted: number;
  needs_fix: number;
  rejected: number;
  stale: number;
  per_paper: Record<string, { claims: number; audited: number; accepted: number }>;
  auditors: string[];
};

export type CorpusSummaryV2 = {
  notice: string;
  built_on: string;
  papers: number;
  excluded: number;
  experiments: number;
  results: number;
  quotes: number;
  conflicts: number;
  reporting: Record<string, number>;
  tasks: Record<string, number>;
  families: Record<string, number>;
  metrics: Record<string, number>;
  cells: number;
  shared_cells: number;
  figures_only: string[];
  recheck: RecheckProgress;
  access: { indexed: number; reachable: number; blocked: number; no_oa: number; unresolved: number } | null;
  audit: AuditProgress;
};

const TIMEOUT_MS = 20_000;

async function v2<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (error) {
    // A refused connection must not read as an empty corpus.
    throw new ApiError(error instanceof Error ? error.message : "network error", 0);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.error?.message ?? `HTTP ${response.status}`, response.status);
  }
  return response.json();
}

export function getCorpusSummary(): Promise<CorpusSummaryV2> {
  return v2("/api/v2/summary");
}

export function listCorpusV2Papers(options: { q?: string; task?: string; family?: string } = {}) {
  const query = new URLSearchParams({ limit: "500" });
  if (options.q) query.set("q", options.q);
  if (options.task) query.set("task", options.task);
  if (options.family) query.set("family", options.family);
  return v2<{
    notice: string; total: number; tasks: string[]; families: string[]; papers: PaperSummaryV2[];
  }>(`/api/v2/papers?${query}`);
}

export function getCorpusV2Paper(slug: string): Promise<PaperDetailV2> {
  return v2(`/api/v2/papers/${encodeURIComponent(slug)}`);
}

export function getReviewQueue(options: { slug?: string; kind?: string; limit?: number } = {}) {
  const query = new URLSearchParams({ limit: String(options.limit ?? 12) });
  if (options.slug) query.set("slug", options.slug);
  if (options.kind) query.set("kind", options.kind);
  return v2<{ notice: string; pending: number; progress: AuditProgress; claims: Claim[] }>(
    `/api/v2/review/queue?${query}`,
  );
}

/** Records one human verdict. Server-side only: the browser never talks to the API directly. */
export function submitVerdict(body: {
  claim_id: string; decision: string; auditor: string; note?: string | null; corrected_value?: unknown;
}) {
  return v2<{ verdict: Verdict; progress: AuditProgress }>("/api/v2/review/verdicts", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Human-readable French labels; the vocabularies themselves stay machine-stable. */
export const KIND_LABEL: Record<Claim["kind"], string> = {
  RESULT: "Résultat mesuré",
  TRAINING: "Réglage d’entraînement",
  TRAINING_EXTRA: "Preuve complémentaire",
  METHOD: "Méthode",
  DATASET: "Jeu de données",
  LIMITATION: "Limite annoncée",
  CONFLICT: "Valeurs contradictoires",
  EXCLUSION: "Papier écarté",
  OTHER: "Autre",
};

export const RECHECK_LABEL: Record<RecheckState, string> = {
  CONFIRMED: "contre-vérifiée : la seconde lecture confirme le contexte",
  SUSPECT: "signalée par la seconde lecture, non tranchée",
  SUSPECT_APPLIED: "signalée par la seconde lecture, l’enregistrement a été corrigé",
  SUSPECT_KEPT: "signalée par la seconde lecture, signalement écarté après relecture",
  UNREADABLE: "page trop abîmée pour une seconde lecture",
  STALE: "la valeur a changé depuis la contre-vérification",
  NOT_RECHECKED: "pas encore contre-vérifiée",
};

export const DECISION_LABEL: Record<string, string> = {
  ACCEPTED: "Confirmé",
  NEEDS_FIX: "À corriger",
  REJECTED: "Rejeté",
  UNAUDITED: "À vérifier",
  STALE: "À revérifier",
};

export const TASK_LABEL: Record<string, string> = {
  FORECASTING: "Prévision",
  DATA_ASSIMILATION: "Assimilation",
  GAP_FILLING_RECONSTRUCTION: "Reconstruction de trous",
  SUPER_RESOLUTION: "Super-résolution",
  BATHYMETRY_ESTIMATION: "Bathymétrie",
  CLASSIFICATION_SEGMENTATION: "Classification",
  DETECTION: "Détection",
  PARAMETERIZATION: "Paramétrisation",
  BIAS_CORRECTION: "Correction de biais",
  EMULATION_SURROGATE: "Émulation",
  INVERSE_INFERENCE: "Inversion",
  OTHER: "Autre",
};

export function taskLabel(task: string): string {
  return TASK_LABEL[task] ?? task;
}

export const FAMILY_LABEL: Record<string, string> = {
  CNN_UNET: "U-Net",
  CNN_AUTOENCODER: "auto-encodeur convolutif",
  CNN_GENERIC: "réseau convolutif",
  MLP_DNN: "perceptron multicouche",
  TRANSFORMER: "transformeur",
  FNO_NEURAL_OPERATOR: "opérateur neuronal de Fourier",
  NEURAL_ODE: "équation différentielle neuronale",
  GNN: "réseau de graphes",
  RNN_LSTM_GRU: "réseau récurrent (LSTM/GRU)",
  CNN_RNN_HYBRID: "convolutif + récurrent",
  DIFFUSION: "modèle de diffusion",
  GAN: "réseau antagoniste",
  SYMBOLIC_REGRESSION: "régression symbolique",
  HYBRID_PHYSICS_ML: "hybride physique + apprentissage",
  VARIATIONAL_ANALYSIS: "analyse variationnelle",
  CLASSICAL_ML: "apprentissage classique",
  CLASSICAL_BASELINE: "référence sans apprentissage",
  OTHER: "autre",
};

export function familyLabel(family: string): string {
  return FAMILY_LABEL[family] ?? family.toLowerCase().replace(/_/g, " ");
}

/** Field names as the extraction contract spells them, in plain French. */
export const FIELD_LABEL: Record<string, string> = {
  canonical_name: "nom",
  family: "famille",
  architecture_note: "architecture",
  spatial_resolution: "résolution spatiale",
  temporal_resolution: "résolution temporelle",
  region: "zone",
  variables: "variables",
  period_start: "début de période",
  period_end: "fin de période",
  role: "rôle",
  loss: "fonction de coût",
  optimizer: "optimiseur",
  learning_rate: "taux d’apprentissage",
  batch_size: "taille de lot",
  epochs: "époques",
  hardware: "matériel",
};

export const ROLE_LABEL: Record<string, string> = {
  PRIMARY_TRAINING: "entraînement principal",
  EVALUATION: "évaluation",
  AUXILIARY_COVARIABLE: "covariable auxiliaire",
  BASELINE_PRODUCT: "produit de référence",
};

export function roleLabel(role: string): string {
  return ROLE_LABEL[role] ?? role.toLowerCase().replace(/_/g, " ");
}

export function fieldLabel(field: string): string {
  return FIELD_LABEL[field] ?? field.replace(/_/g, " ");
}

/* ---------- vues par entité (issues #22, #23) ---------- */

export type EntityKind = "family" | "task" | "dataset" | "dataset_group" | "variable" | "method";

export type Reporting = Record<string, { reported: number; of: number }>;

export type EntitySummary = {
  name: string;
  papers: number;
  experiments: number;
  results: number;
  tasks: Record<string, number>;
  families: Record<string, number>;
  datasets: Record<string, number>;
  variables: Record<string, number>;
  methods: Record<string, number>;
  metrics: Record<string, number>;
  reporting: Reporting;
};

export type EntityDetail = EntitySummary & {
  kind: EntityKind;
  paper_list: Array<{ slug: string; title: string; year: number | null }>;
  experiment_list: Array<{
    slug: string; id: string; task: string; method: string | null; family: string | null;
    datasets: string[]; variable: string | null; reported: string[]; missing: string[]; results: number;
  }>;
  problems: Array<{ theme: string; slug: string; title: string; quote: string | null; page: number | null }>;
  comparability: string;
};

export type Analysis = {
  notice: string;
  entities: Record<EntityKind, EntitySummary[]>;
  coverage: {
    tasks: string[];
    families: string[];
    matrix: Array<{ task: string; cells: Array<{ family: string; papers: number }> }>;
    empty_cells: Array<{ task: string; family: string }>;
    caveat: string;
  };
  problems: Record<string, {
    papers: number;
    items: Array<{ slug: string; title: string; quote: string | null; page: number | null }>;
  }>;
};

export function getAnalysis(): Promise<Analysis> {
  return v2("/api/v2/analysis");
}

export function getEntity(kind: EntityKind, name: string): Promise<EntityDetail> {
  return v2(`/api/v2/entities/${kind}/${encodeURIComponent(name)}`);
}

export const ENTITY_LABEL: Record<EntityKind, string> = {
  family: "architecture",
  task: "objectif",
  dataset: "jeu de données (nom du papier)",
  dataset_group: "source de données",
  variable: "variable prédite",
  method: "méthode nommée",
};

export const THEME_LABEL: Record<string, string> = {
  DATA: "données",
  COMPUTE: "calcul",
  GENERALIZATION: "généralisation",
  PHYSICS: "physique",
  UNCERTAINTY: "incertitude",
  REPRODUCIBILITY: "reproductibilité",
  EVALUATION: "évaluation",
  FUTURE_WORK: "suite annoncée",
  OTHER: "autre",
};

/** The label a page shows for an entity name, by kind. */
export function entityName(kind: EntityKind, name: string): string {
  if (kind === "family") return familyLabel(name);
  if (kind === "task") return taskLabel(name);
  return name;
}

/* ---------- interroger le corpus (issue #24) ---------- */

export type AskUnderstood = {
  fields: string[]; themes: string[]; tasks: string[]; families: string[];
  dataset_groups: string[]; variables: string[]; methods: string[];
};

export type AskBlock =
  | { kind: "training"; field: string; reported: number; of: number; values: Array<{
      slug: string; title: string; experiment: string; task: string; family: string | null;
      method: string | null; value: unknown; unit: string | null; page: number | null;
      quote: string | null; note: string | null;
    }> }
  | { kind: "results"; count: number; values: Array<{
      slug: string; title: string; experiment: string; metric: string | null;
      metric_raw: string | null; value: number | null; unit: string | null; split: string | null;
      config: string | null; baseline_name: string | null; baseline_value: number | null;
      page: number | null; quote: string | null;
    }> }
  | { kind: "limitations"; count: number; values: Array<{
      slug: string; title: string; theme: string; quote: string | null; page: number | null;
    }> }
  | { kind: "experiments"; count: number; values: Array<{
      slug: string; title: string; experiment: string; task: string; family: string | null;
      method: string | null; datasets: string[]; variable: string | null; reported: string[];
    }> };

export type AskAnswer = {
  question: string;
  understood: AskUnderstood;
  understood_nothing: boolean;
  experiments_matched: number;
  papers_matched: number;
  answers: AskBlock[];
  caveats: string[];
};

export function askCorpus(question: string): Promise<AskAnswer> {
  return v2(`/api/v2/ask?q=${encodeURIComponent(question)}`);
}
