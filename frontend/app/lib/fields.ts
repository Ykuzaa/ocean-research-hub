import type { EvidenceField, PaperRecord } from "@/app/lib/api";

export const SECTIONS = [
  { key: "scientific_framing", title: "Contexte scientifique" },
  { key: "data", title: "Données" },
  { key: "architecture", title: "Architecture" },
  { key: "training", title: "Entraînement" },
  { key: "objective", title: "Fonction de perte" },
  { key: "evaluation", title: "Évaluation" },
  { key: "results", title: "Résultats" },
  { key: "limitations", title: "Limites" },
] as const;

const LABELS: Record<string, string> = {
  "scientific_framing.problem": "Problème",
  "scientific_framing.motivation": "Motivation",
  "scientific_framing.objective": "Objectif",
  "scientific_framing.task_type": "Type de tâche",
  "scientific_framing.domain": "Domaine",
  "scientific_framing.region": "Région",
  "scientific_framing.ocean_regime": "Régime océanique",
  "data.datasets": "Datasets",
  "data.origins": "Origine des données",
  "data.variables": "Variables",
  "data.units": "Unités",
  "data.inputs": "Entrées",
  "data.outputs": "Sorties",
  "data.depth_levels": "Niveaux de profondeur",
  "data.spatial_resolution": "Résolution spatiale",
  "data.temporal_resolution": "Résolution temporelle",
  "data.time_coverage": "Période couverte",
  "data.sample_counts": "Nombre d'échantillons",
  "data.splits.train": "Période d'entraînement",
  "data.splits.validation": "Période de validation",
  "data.splits.test": "Période de test",
  "data.preprocessing.missing_data": "Données manquantes",
  "data.preprocessing.masking": "Masquage",
  "data.preprocessing.regridding": "Regridding",
  "data.preprocessing.interpolation": "Interpolation",
  "data.preprocessing.normalization": "Normalisation",
  "data.preprocessing.anomalies": "Anomalies",
  "data.preprocessing.filtering": "Filtrage",
  "data.preprocessing.augmentation": "Augmentation",
  "data.preprocessing.derived_features": "Variables dérivées",
  "architecture.family": "Famille de modèle",
  "architecture.summary": "Résumé",
  "architecture.encoder": "Encodeur",
  "architecture.decoder": "Décodeur",
  "architecture.blocks": "Blocs",
  "architecture.layer_count": "Nombre de couches",
  "architecture.hidden_dimensions": "Dimensions cachées",
  "architecture.channels": "Canaux",
  "architecture.patch_or_window": "Patch / fenêtre",
  "architecture.attention": "Attention",
  "architecture.positional_encoding": "Encodage positionnel",
  "architecture.skip_connections": "Skip connections",
  "architecture.activations": "Activations",
  "architecture.normalization_layers": "Normalisation",
  "architecture.dropout": "Dropout",
  "architecture.parameter_count": "Nombre de paramètres",
  "architecture.forecasting_mode": "Mode de prévision",
  "architecture.probabilistic_mode": "Déterministe / probabiliste",
  "architecture.physical_components": "Composantes physiques",
  "training.optimizer": "Optimiseur",
  "training.learning_rate": "Learning rate",
  "training.scheduler": "Scheduler",
  "training.batch_size": "Batch size",
  "training.epochs_or_steps": "Époques / itérations",
  "training.early_stopping": "Early stopping",
  "training.weight_decay": "Weight decay",
  "training.gradient_clipping": "Gradient clipping",
  "training.initialization": "Initialisation",
  "training.mixed_precision": "Précision mixte",
  "training.random_seeds": "Seeds",
  "training.hardware": "Matériel",
  "training.gpu_count": "Nombre de GPU",
  "training.gpu_types": "Type de GPU",
  "training.training_time": "Temps d'entraînement",
  "objective.primary_loss": "Loss principale",
  "objective.auxiliary_losses": "Losses auxiliaires",
  "objective.physics_constraints": "Contraintes physiques",
  "objective.spectral_losses": "Losses spectrales",
  "objective.gradient_front_losses": "Losses gradients / fronts",
  "objective.probabilistic_losses": "Losses probabilistes",
  "objective.loss_weights": "Pondérations",
  "evaluation.baselines": "Baselines",
  "evaluation.metrics": "Métriques",
  "evaluation.forecast_horizon": "Horizon de prévision",
  "evaluation.evaluation_datasets": "Données d'évaluation",
  "evaluation.observation_space_validation": "Validation sur observations",
  "evaluation.uncertainty_calibration": "Calibration de l'incertitude",
  "evaluation.ablations": "Ablations",
  "evaluation.ood_tests": "Tests hors distribution",
  "evaluation.statistical_significance": "Significativité statistique",
  "results.headline": "Résultats clés",
  "results.by_variable": "Par variable",
  "results.by_region": "Par région",
  "results.by_depth": "Par profondeur",
  "results.by_horizon": "Par horizon",
  "results.qualitative": "Observations qualitatives",
  "results.compute_cost": "Coût de calcul",
  "limitations.author_reported": "Limites citées par les auteurs",
  "limitations.future_work": "Travaux futurs",
  "limitations.reproducibility": "Reproductibilité",
  "limitations.data": "Données",
  "limitations.physics": "Physique",
  "limitations.generalization": "Généralisation",
  "limitations.uncertainty": "Incertitude",
  "limitations.compute": "Calcul",
  "limitations.ai_interpretation": "Interprétation IA",
  "limitations.team_note": "Note d'équipe",
};

export type FieldEntry = { path: string; label: string; field: EvidenceField };

function isEvidenceField(node: unknown): node is EvidenceField {
  return typeof node === "object" && node !== null && "status" in node && "source" in node;
}

export function hasContent(field: EvidenceField | undefined): boolean {
  if (!field) return false;
  return (field.value !== null && field.value !== undefined) || field.conflict_values.length > 0;
}

function labelFor(path: string): string {
  const last = path.split(".").at(-1) ?? path;
  return LABELS[path] ?? last.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** Every leaf field of a section, in schema order, with or without content. */
export function sectionEntries(record: PaperRecord, sectionKey: string): FieldEntry[] {
  const entries: FieldEntry[] = [];
  const walk = (node: unknown, path: string) => {
    if (isEvidenceField(node)) {
      entries.push({ path, label: labelFor(path), field: node });
    } else if (typeof node === "object" && node !== null) {
      for (const [key, child] of Object.entries(node)) walk(child, `${path}.${key}`);
    }
  };
  walk(record[sectionKey], sectionKey);
  return entries;
}

export function fieldAt(record: PaperRecord, path: string): EvidenceField | undefined {
  let node: unknown = record;
  for (const key of path.split(".")) {
    if (typeof node !== "object" || node === null) return undefined;
    node = (node as Record<string, unknown>)[key];
  }
  return isEvidenceField(node) ? node : undefined;
}

export function paperTitle(record: PaperRecord): string | null {
  const title = fieldAt(record, "paper.title")?.value;
  return typeof title === "string" ? title : null;
}

export function formatAuthors(authors: string[], max = 3): string {
  if (authors.length <= max) return authors.join(", ");
  return `${authors.slice(0, max).join(", ")} et ${authors.length - max} autres`;
}
