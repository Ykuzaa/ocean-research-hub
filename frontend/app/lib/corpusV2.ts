/**
 * Corpus v2 client: records whose every value carries the sentence it was read from.
 *
 * The backend re-locates each quote on the page it cites before the corpus is committed,
 * so a value displayed here is *sourced*. It is *audited* only when `audit_state` says a
 * person checked it — the two are never collapsed into one badge.
 */
import { API_BASE_URL, ApiError } from "./api";

export type AuditState = "UNAUDITED" | "STALE" | "ACCEPTED" | "NEEDS_FIX" | "REJECTED";

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
