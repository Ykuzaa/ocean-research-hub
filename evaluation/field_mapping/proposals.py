"""AI_INTERPRETATION proposals for the 909 B16 FIELD_PATH_MAP paths without a canonical field.

Every path not listed in MAPPED or UNMAPPED stays AMBIGUOUS (pending). Policy:
P1 MAPPED only if the source path is a synonym of the canonical field, or the canonical
   field is a heterogeneous container (results, baselines, metrics, variables, encoder,
   decoder, limitations, loss weights, ...) and the original path stays visible.
   A qualifier that changes the quantity (component, stage, variant, max vs actual,
   per-GPU, horizon into a non-container) keeps the path AMBIGUOUS.
P2 AI_INTERPRETATION rows map only into interpretation.*; conflict/extraction-check
   annotations are UNMAPPED (they belong in conflict review, not in a field value).
P3 Guards (applied in build.py): search-space / code-config-not-linked / HPO-budget scopes,
   claim types incompatible with the target, review-level scopes into paper-level
   limitations/results, and mixed claim types all force AMBIGUOUS.
"""

MAPPED = {
    # ablations / evaluation ablations -> results.ablation
    **{p: "results.ablation" for p in [
        "ablations.components", "ablations.design", "ablations.domain_size", "ablations.factors",
        "ablations.inputs", "ablations.preprocessing", "ablations.solver_iterations",
        "ablations.strategies", "ablations.mode_interactions", "evaluation.ablations"]},
    # architecture
    "architecture.afno_depth": "architecture.num_layers",
    "architecture.bias_initialization": "training.initialization",
    "architecture.family": "architecture.method_family",
    "architecture.type": "architecture.method_family",
    "architecture.model": "architecture.method_family",
    "architecture.feature_extractor": "architecture.backbone",
    "architecture.hidden_dimensions": "architecture.hidden_width",
    "architecture.normalization": "architecture.normalization_layer",
    "architecture.parameters": "architecture.parameter_count",
    "architecture.policy": "rl.policy_architecture",
    "architecture.sfno_block": "architecture.block_type",
    **{p: "architecture.decoder" for p in [
        "architecture.decoder_blocks", "architecture.decoder_layers",
        "architecture.decoder_output_length", "architecture.decoder_parameters",
        "architecture.decoder_stages", "architecture.decoder_transpose",
        "architecture.decoder_transpose_kernel", "architecture.decoder_transpose_stride"]},
    **{p: "architecture.encoder" for p in [
        "architecture.encoder_channels", "architecture.encoder_conv_layers",
        "architecture.encoder_convolutions", "architecture.encoder_count",
        "architecture.encoder_kernel", "architecture.encoder_layers",
        "architecture.encoder_parameters", "architecture.encoder_pooling",
        "architecture.encoder_stages"]},
    # baselines
    "baselines": "evaluation.baselines",
    "baselines.list": "evaluation.baselines",
    "baselines.pixel_model": "evaluation.baselines",
    "boundary_conditions": "physics.boundary_conditions",
    # data
    "data.geographic_region": "problem.geography",
    "data.modalities": "data.data_source",
    "data.pressure_level_count": "data.vertical_levels",
    "data.vertical_level_count": "data.vertical_levels",
    "data.regridding": "data.interpolation",
    # datasets
    "datasets.name": "data.dataset_name",
    "datasets.source": "data.dataset_name",
    "datasets.sources": "data.dataset_name",
    "datasets.data_archive": "reproducibility.data_url",
    "datasets.depth_levels": "data.vertical_levels",
    "datasets.vertical_layers": "data.vertical_levels",
    "datasets.vertical_levels": "data.vertical_levels",
    "datasets.domain": "problem.geography",
    "datasets.geography": "problem.geography",
    "datasets.region": "problem.geography",
    "datasets.labels": "data.target_source",
    "datasets.period": "problem.study_period",
    "datasets.period_used": "problem.study_period",
    "datasets.reported_split": "data.split_strategy",
    "datasets.split": "data.split_strategy",
    "datasets.training_validation_split": "data.split_strategy",
    "datasets.validation_split": "data.split_strategy",
    "datasets.resolution": "data.spatial_resolution",
    "datasets.spatial_grids": "data.spatial_resolution",
    "datasets.spatial_resolution": "data.spatial_resolution",
    "datasets.spatial_resolutions": "data.spatial_resolution",
    "datasets.temporal_resolution": "data.temporal_resolution",
    "datasets.temporal_resolutions": "data.temporal_resolution",
    "datasets.test_period": "data.test_period",
    "datasets.test_years": "data.test_period",
    "datasets.train_period": "data.train_period",
    "datasets.training_period": "data.train_period",
    "datasets.validation_period": "data.validation_period",
    "datasets.validation_year": "data.validation_period",
    # evaluation
    "evaluation.forecast_horizon": "problem.forecast_horizon",
    # future work (field mapping only; provenance class stays verbatim)
    "future_work": "limitations.future_work",
    **{p: "limitations.future_work" for p in [
        "future_work.angle_representation", "future_work.domain_adaptation",
        "future_work.explainability", "future_work.global", "future_work.hybrid_da",
        "future_work.multisensor", "future_work.noisy_swot", "future_work.observations",
        "future_work.physics", "future_work.predictors", "future_work.probabilistic",
        "future_work.release", "future_work.reproducibility", "future_work.residuals",
        "future_work.robustness", "future_work.satellite_data", "future_work.ssh",
        "future_work.training_data"]},
    # AI-interpreted research gaps
    **{p: "interpretation.candidate_research_gaps" for p in [
        "gap.domain_shift", "gap.extremes", "gap.sparsity", "gap.stability",
        "research_gap", "research_gap.candidate"]},
    # inference cost
    "inference.cost": "results.runtime",
    "inference.cpu_time": "results.runtime",
    "inference.time_2021": "results.runtime",
    # inputs
    "inputs": "data.input_variables",
    "inputs.variables": "data.input_variables",
    "inputs.variable": "data.input_variables",
    "inputs.air_temperature": "data.input_variables",
    "inputs.cloud_cover": "data.input_variables",
    "inputs.pressure": "data.input_variables",
    "inputs.wind": "data.input_variables",
    "inputs.atmospheric_forcing": "data.input_variables",
    "inputs.profiles": "data.input_variables",
    "inputs.scalars": "data.input_variables",
    "inputs.text_fields": "data.input_variables",
    "inputs.tensor_shape": "architecture.input_shape",
    # loss
    "loss.total": "objective.total_loss",
    "loss.component_fit": "objective.data_loss",
    "loss.component_observation": "objective.data_loss",
    "loss.observation_component": "objective.data_loss",
    "objective.observation_loss": "objective.data_loss",
    "loss.sensor_component": "objective.data_loss",
    "loss.component_reconstruction": "objective.reconstruction_loss",
    "loss.component_regularization": "objective.regularization",
    "loss.regularization_component": "objective.regularization",
    "regularization.derivatives": "objective.regularization",
    "loss.deterministic_spectral": "objective.spectral_loss",
    "loss.masking": "objective.masking_in_loss",
    **{p: "objective.loss_weights" for p in [
        "loss.physics1_weight", "loss.physics2_weight", "loss.regularization_weight",
        "loss.sensor_weight", "loss.weight_boundary", "loss.weight_l2",
        "loss.constraint_lambda", "loss.weight_selection"]},
    # metrics
    **{p: "evaluation.metrics" for p in [
        "metrics.list", "metrics.names", "metrics.mae", "metrics.pointwise", "metrics.primary",
        "metrics.sic_rmse", "metrics.similarity", "metrics.interannual_score", "metrics.detection"]},
    "metrics.bootstrap_interval": "evaluation.significance",
    "metrics.uncertainty": "evaluation.significance",
    # outputs
    **{p: "data.output_variables" for p in [
        "outputs", "outputs.variables", "outputs.variable", "outputs.sst", "outputs.prognostic_2d",
        "outputs.prognostic_3d", "outputs.groups", "outputs.chlorophyll_units", "outputs.target",
        "outputs.residual"]},
    "outputs.tendency_unit": "data.output_units",
    "outputs.horizon": "problem.forecast_horizon",
    "outputs.rollout": "architecture.autoregressive",
    "outputs.tensor_shape": "architecture.output_shape",
    # physics
    "physics.boundary_data": "physics.boundary_conditions",
    "physics.boundary_ocean": "physics.boundary_conditions",
    "physics.boundary_atmosphere": "physics.boundary_conditions",
    "physics.derivatives": "physics.numerical_discretization",
    # preprocessing
    **{p: "data.normalization" for p in [
        "preprocessing.normalization", "preprocessing.output_standardization",
        "preprocessing.interface_normalization", "preprocessing.pixel_scaling",
        "preprocessing.velocity_scaling"]},
    "preprocessing.scaling_fit": "data.data_leakage_controls",
    "preprocessing.interpolation": "data.interpolation",
    "preprocessing.grid": "data.interpolation",
    **{p: "data.masking" for p in [
        "preprocessing.land", "preprocessing.land_mask", "preprocessing.masks",
        "preprocessing.land_value"]},
    **{p: "data.missingness" for p in [
        "preprocessing.missing_anomaly", "preprocessing.missing_chlorophyll",
        "preprocessing.missing_values", "preprocessing.missingness"]},
    "preprocessing.flips": "training.augmentation",
    "preprocessing.mosaic_probability": "training.augmentation",
    # problem
    "problem.objective": "problem.research_question",
    "problem.domain": "problem.primary_domain",
    "problem.region": "problem.geography",
    "problem.formulation": "architecture.autoregressive",
    # regularization
    "regularization": "training.weight_decay",
    "regularization.early_stopping": "training.early_stopping",
    "regularization.gradient_clipping": "training.gradient_clipping",
    # reproducibility
    **{p: "reproducibility.code_url" for p in [
        "reproducibility.code_archive", "reproducibility.code_online",
        "reproducibility.code_training", "reproducibility.capsule",
        "reproducibility.inference_code", "reproducibility.dynamical_core"]},
    "reproducibility.figure_data": "reproducibility.data_url",
    "reproducibility.framework": "reproducibility.dependencies",
    "reproducibility.software": "reproducibility.dependencies",
    "reproducibility.metadata_license": "reproducibility.license",
    # results
    "results.inference_time": "results.runtime",
    "results.speed": "results.runtime",
    "results.relative_cost": "results.runtime",
    "results.transfer": "results.generalization",
    "results.significance": "evaluation.significance",
    "results.rmse_vs_climatology_fig2a": "evaluation.skill_vs_baseline",
    # RL
    "rl.action": "rl.action_space",
    "rl.state": "rl.state_space",
    "rl.reward": "rl.reward_formula",
    "rl.reward_component_accuracy": "rl.reward_components",
    "rl.reward_component_diversity": "rl.reward_components",
    # training
    "training.adaboost_search": "training.hyperparameter_search",
    "training.lstm_search": "training.hyperparameter_search",
    "training.adaptation": "training.fine_tuning",
    "training.batch": "training.batch_size",
    "training.cross_validation": "data.split_strategy",
    "training.early_stopping_patience": "training.early_stopping",
    "training.gpu_memory_reported": "training.gpu_memory",
    "training.hardware": "training.training_hardware",
    "training.hardware_as_printed": "training.training_hardware",
    "training.hardware_finetuning": "training.training_hardware",
    "training.hardware_pretraining": "training.training_hardware",
    "training.precision": "training.precision_mode",
    "training.scheduler": "training.lr_schedule",
    "training.scheduler_factor": "training.lr_schedule",
    "training.scheduler_patience": "training.lr_schedule",
    "training.warmup_epochs": "training.lr_schedule",
    "training.warmup_steps": "training.lr_schedule",
    "training.steps": "training.iterations",
    "training.time": "training.training_time",
    "training.total_time": "training.training_time",
}

# Numeric / reported results go to the heterogeneous results container; the original
# path (horizon, variable, figure, table) remains the qualifier.
RESULTS_CONTAINER = [
    "results.Z500.RMSE_72h", "results.anosim", "results.argo_effect", "results.argo_effect_p15",
    "results.argo_effect_p18", "results.baseline_map", "results.confusion_matrix",
    "results.correlation_ssh", "results.currents", "results.daily_surface_correlation",
    "results.detection_accuracy", "results.detections", "results.eof", "results.error",
    "results.error_reduction", "results.example_niiee_model", "results.example_niiee_persistence",
    "results.free_antarctic_rmse", "results.free_arctic_rmse", "results.highlat_dnn_u_rmse",
    "results.highlat_swot_u_rmse", "results.improvement", "results.iod_spatial_correlation",
    "results.lowlat_lgb_u_rmse", "results.lowlat_lgb_v_rmse", "results.mae_day1", "results.map",
    "results.mean_test_ssp_case_a", "results.meridional_velocity.log_1_minus_ACC",
    "results.meridional_velocity.log_RSE", "results.mhw_detection", "results.ohc_correlation",
    "results.precision_oiednet", "results.r2_day10", "results.recall_oiednet", "results.rmse",
    "results.rmse_corrected_24h", "results.rmse_corrected_72h", "results.rmse_day10",
    "results.rmse_hs", "results.rmse_original_24h", "results.rmse_original_72h",
    "results.rmse_t60_fig2b", "results.rmse_tm", "results.rmse_u", "results.rmse_v",
    "results.salinity.log_1_minus_ACC", "results.salinity.log_RSE", "results.skill",
    "results.skill_horizon", "results.soda_correlation_no_transfer",
    "results.soda_correlation_transfer", "results.steric_height", "results.table1",
    "results.table_s2_example", "results.table_s5_global", "results.table_s5_regional",
    "results.temperature.log_1_minus_ACC", "results.temperature.log_RSE", "results.test",
    "results.test_range_si", "results.trend", "results.uncertainty",
    "results.useful_forecast_lead", "results.validation_mean_iou",
    "results.zonal_velocity.log_1_minus_ACC", "results.zonal_velocity.log_RSE",
]
MAPPED.update({p: "results.quantitative_results" for p in RESULTS_CONTAINER})

UNMAPPED = {
    "applicability.rl": "Applicability finding (NOT_APPLICABLE); needs the pending NOT_APPLICABLE status decision (#29 item 3), not a field value.",
    "methods.own_experiments": "Applicability finding (NOT_APPLICABLE); needs the pending NOT_APPLICABLE status decision (#29 item 3).",
    "architecture.legacy_conflict": "Conflict annotation; belongs in conflict review, not a field value.",
    "claim_check": "Extraction-check annotation (AI_INTERPRETATION), not a paper value.",
    "data.caption_check": "Extraction-check annotation (possible typo), not a paper value.",
    "data.conflict_review": "Conflict-review annotation; must stay a visible CONFLICT review, not a field value.",
    "data.conflict_si_vs_text": "Conflict annotation; belongs in conflict review.",
    "data.conflict_training_period": "Conflict annotation; belongs in conflict review.",
    "data.conflict_trend_increase": "Conflict annotation; belongs in conflict review.",
    "extraction.model_scope": "Extraction metadata (AI_INTERPRETATION), not a paper value.",
    "loss.specification_caveat": "Extraction caveat (AI_INTERPRETATION), not a paper value.",
    "metrics.equation_check": "Extraction-check annotation, not a paper value.",
    "preprocessing.time_window_conflict": "Conflict annotation; belongs in conflict review.",
    "reproducibility.split_conflict": "Conflict annotation; belongs in conflict review.",
    "reproducibility.supplement_search": "Source-access note, not a paper value.",
    "results.percentage_conflict": "Conflict annotation; belongs in conflict review.",
    "architecture.baseline_ann": "Describes a baseline; mapping into architecture.* would attribute it to the studied model.",
}

# Reasons for notable AMBIGUOUS decisions (everything else gets the default reason).
AMBIGUOUS_REASONS = {
    "reproducibility.code": "Mostly code URLs, but includes non-URL availability statements (e.g. OAI-0028 'no code repository located'); needs per-claim split before mapping to reproducibility.code_url.",
    "reproducibility.data": "Mixes URLs and availability statements ('On request; not public'); needs per-claim decision before reproducibility.data_url.",
    "training.max_epochs": "Maximum epochs is not the number of epochs trained (early stopping); training.epochs would change meaning.",
    "training.maximum_epochs": "Maximum epochs is not the number of epochs trained; training.epochs would change meaning.",
    "training.batch_size_local": "Per-GPU batch is not the global batch size.",
    "training.time_pretraining": "Stage-specific time; training.training_time would read as total training time.",
    "training.time_finetuning": "Stage-specific time; training.training_time would read as total training time.",
    "architecture.hidden_layers": "Hidden-layer count is not total layer count (architecture.num_layers).",
    "architecture.embedding_dim": "Treating embedding dimension as hidden width is a convention, not a reported equivalence.",
    "architecture.embedding_dimension": "Treating embedding dimension as hidden width is a convention, not a reported equivalence.",
    "architecture.patch_size": "Contract gap: no patch/window-size field.",
    "architecture.positional_encoding": "Contract gap: no positional-encoding field.",
    "architecture.dropout": "Contract gap: no dropout field.",
    "architecture.drop_path": "Contract gap: no drop-path/stochastic-depth field.",
    "regularization.dropout": "Contract gap: no dropout field.",
    "regularization.drop_path": "Contract gap: no drop-path field.",
    "regularization.droppath": "Contract gap: no drop-path field.",
    "datasets.training": "Role-qualified dataset (training); data.dataset_name would drop the role.",
    "datasets.observations": "Role-qualified datasets (observations/verification); mapping would drop the role.",
    "datasets.reference": "Reference may mean verification truth or baseline; ambiguous role.",
    "baselines.reference": "Reference may mean verification truth or baseline; ambiguous role.",
    "inputs.history": "Contract gap: no input-window/history-length field.",
    "inputs.window": "Contract gap: no input-window field.",
    "inputs.observations": "In DA papers these are assimilated observations, not ML input variables.",
    "outputs.lead_range": "Lead range sits between problem.forecast_horizon and evaluation.forecast_lead; human choice needed.",
    "preprocessing.augmentation": "Mixed: one claim is an iterative DA/CNN retraining procedure, not data augmentation.",
    "loss.mask": "Optional code flag; not established as used in the paper's experiment.",
    "inference.rollout": "Describes iterative feeding; labelling it architecture.autoregressive is left to a human.",
    "architecture.padding": "Padding vs architecture.boundary_handling equivalence is a convention.",
    "assimilation.method": "Contract gap: no data-assimilation block.",
}
DEFAULT_AMBIGUOUS = ("No contract field without narrowing or losing the qualifier in the source path; "
                     "left pending (#29: when unsure, leave unmapped).")
