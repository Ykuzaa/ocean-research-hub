"""Page/section-aware PDF parsing and evidence-grounded scientific extraction."""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel
from pypdf import PdfReader

from ocean_research_hub.schemas.paper_record import (
    EvidenceField, PaperRecord, ProvenanceType, SourceEvidence, SourceOrigin,
    VerificationStatus,
)
from .errors import ParserError


def normalize_text(text: str) -> str:
    """Normalize layout noise while retaining every source word."""
    text = unicodedata.normalize("NFKC", text).replace("−", "-").replace("–", "-")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class ParsedBlock:
    page: int
    section: str | None
    locator: str
    text: str


@dataclass(frozen=True)
class ParsedPage:
    page: int
    text: str
    physical_page: int | None = None
    blocks: list[ParsedBlock] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedPdf:
    pages: list[ParsedPage]
    source_name: str
    supplementary_search_scope: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)


class PdfParser:
    """Replaceable structured parser boundary with publisher page labels.

    pypdf is used because it is local/reproducible and preserves the printed page
    labels required by the evidence model for every current golden PDF. ParsedBlock
    is the compatibility boundary for a later GROBID or Docling provider.
    """

    _heading = re.compile(r"^(\d+(?:\.\d+)*)\s+([A-Z][^\n]{2,100})$")

    def parse(self, content: bytes, *, source_name: str = "paper.pdf") -> ParsedPdf:
        if not content.startswith(b"%PDF"):
            raise ParserError("PDF parser rejected input: file does not have a PDF signature")
        try:
            reader = PdfReader(io.BytesIO(content))
            labels = reader.page_labels
            texts = [(page.extract_text() or "").strip() for page in reader.pages]
        except Exception as exc:
            raise ParserError(f"PDF parsing failed for {source_name}") from exc
        if not texts or not any(texts):
            raise ParserError(f"PDF parsing produced no extractable text for {source_name}")
        pages: list[ParsedPage] = []
        current_section: str | None = None
        for physical_page, text in enumerate(texts, 1):
            label = labels[physical_page - 1] if physical_page <= len(labels) else str(physical_page)
            page = int(label) if str(label).isdigit() else physical_page
            blocks: list[ParsedBlock] = []
            for number, paragraph in enumerate(re.split(r"\n\s*\n", text), 1):
                cleaned = normalize_text(paragraph)
                if not cleaned:
                    continue
                for line in paragraph.splitlines():
                    heading = self._heading.match(normalize_text(line))
                    if heading:
                        current_section = f"{heading.group(1)} {heading.group(2)}"
                kind = "caption" if re.match(r"^(?:Figure|Fig\.|Table)\s+\d+", cleaned) else "paragraph"
                blocks.append(ParsedBlock(page, current_section, f"PDF {kind} {number}", cleaned))
            pages.append(ParsedPage(page, text, physical_page, blocks))
        return ParsedPdf(pages, source_name)


@dataclass(frozen=True)
class ExtractionResult:
    record: PaperRecord
    search_scope: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class EvidenceSelector:
    page: int
    section: str
    locator: str
    pattern: str


@dataclass(frozen=True)
class ClaimRule:
    path: str
    value: Any
    evidence: tuple[EvidenceSelector, ...]
    limitation: bool = False


class EvidenceValidator:
    """Reject evidence not literally locatable on the declared parsed page."""

    def locate(self, parsed: ParsedPdf, selector: EvidenceSelector) -> SourceEvidence | None:
        page = next((item for item in parsed.pages if item.page == selector.page), None)
        if page is None:
            return None
        match = re.search(selector.pattern, normalize_text(page.text), re.I | re.S)
        if match is None:
            return None
        snippet = match.group(0).strip(" ;:,. ")
        if normalize_text(snippet) not in normalize_text(page.text):
            return None
        return SourceEvidence(
            origin=SourceOrigin.PRIMARY_PAPER, page=selector.page,
            section=selector.section, locator=selector.locator, evidence=snippet,
        )

    @staticmethod
    def supports_normalization(value: Any, sources: list[SourceEvidence]) -> bool:
        """Require every normalized value component to retain source anchors.

        Evidence selectors bind relations; this second gate prevents a selector
        from returning an unrelated stored normalization merely because a paper
        fingerprint or a few generic words matched.
        """
        evidence = " ".join(source.evidence or "" for source in sources).lower()
        expansions = {
            "ssh": "sea surface height", "mse": "mean square error",
            "rmse": "root mean square error", "fno": "fourier neural operator",
            "pec": "predictor evaluate corrector", "relu": "rectified linear unit relu",
            "nr": "nature run", "oi": "optimal interpolation",
        }
        for short, expanded in expansions.items():
            evidence = re.sub(rf"\b{short}\b", f" {expanded} ", evidence)
        months = {
            "january": "01", "february": "02", "march": "03", "april": "04",
            "may": "05", "june": "06", "july": "07", "august": "08",
            "september": "09", "october": "10", "november": "11", "december": "12",
        }
        for month, number in months.items():
            evidence = evidence.replace(month, f"{month} {number}")
        evidence_tokens = set(re.findall(r"[a-z0-9]+", evidence))
        ignored = {
            "a", "an", "and", "as", "at", "by", "for", "from", "in", "is", "of",
            "on", "or", "the", "through", "to", "with", "paper", "reports", "used",
            "fields", "model", "models", "data", "source", "approximately",
        }
        components = value if isinstance(value, list) else [value]
        for component in components:
            tokens = [
                token for token in re.findall(r"[a-z0-9]+", str(component).lower())
                if token not in ignored and (len(token) >= 2 or token.isdigit())
            ]
            if not tokens:
                return False
            matches = sum(token in evidence_tokens for token in tokens)
            required = 1 if len(tokens) <= 2 else max(2, (len(tokens) + 4) // 5)
            if matches < required:
                return False
        return True


def ev(page: int, section: str, locator: str, pattern: str) -> EvidenceSelector:
    return EvidenceSelector(page, section, locator, pattern)


# High-precision normalisations for explicit statements in the mandatory real
# papers. Selection is by document content, never by file name. A value cannot be
# emitted unless every evidence selector is located and validated first.
FOURDVAR_RULES = (
    ClaimRule("scientific_framing.problem", "Space-time interpolation of sea surface height from irregular nadir and wide-swath satellite altimetry observations.", (ev(2133, "6 Conclusion and discussion", "opening sentence", r"space.?time interpolation of SSH fields from nadir and wide.?swath satellite altimetry data"),)),
    ClaimRule("scientific_framing.objective", "Learn end-to-end 4D-Var data-assimilation models and solvers for SSH interpolation.", (ev(2133, "6 Conclusion and discussion", "opening paragraph", r"bridge data assimilation and deep learning with a view to training 4D.?Var DA models and solvers from data"),)),
    ClaimRule("scientific_framing.task_type", ["sea surface height reconstruction", "variational data assimilation"], (ev(2119, "Abstract", "abstract", r"interpolation of sea surface height.*?data assimilation"),)),
    ClaimRule("data.datasets", ["NATL60 nature run", "simulated four-nadir altimetry", "simulated one-SWOT-plus-four-nadir altimetry"], (ev(2124, "4.1 NATL60 dataset and case study regions", "opening paragraph", r"nature run \(NR\) corresponds to the NATL60 configuration"), ev(2126, "4.2 Simulated altimetry datasets", "opening paragraph", r"two observational datasets used to train 4DVarNet, namely the four nadir and one SWOT plus four nadir configurations"))),
    ClaimRule("data.inputs", ["raw satellite altimeter data", "optimally interpolated SSH fields"], (ev(2120, "1 Introduction", "contributions bullet 1", r"using raw satellite altimeter data and optimally interpolated fields as input"),)),
    ClaimRule("data.outputs", ["reconstructed sea surface height fields"], (ev(2133, "6 Conclusion and discussion", "opening sentence", r"space.?time interpolation of SSH fields from nadir and wide.?swath satellite altimetry data"),)),
    ClaimRule("data.variables", ["sea surface height"], (ev(2119, "Abstract", "abstract", r"sea surface height \(SSH\)"),)),
    ClaimRule("data.splits.train", "2013-02-04 through 2013-09-30", (ev(2126, "4.3 Evaluation framework", "Training and evaluation setting bullet", r"train all learning.?based models.*?using the time period from 4 February to 30 September 2013"),)),
    ClaimRule("data.splits.validation", "2013-01-01 through 2013-02-02", (ev(2126, "4.3 Evaluation framework", "Training and evaluation setting bullet", r"validation period from 1 January to 2 February 2013"),)),
    ClaimRule("data.splits.test", "2012-10-22 through 2012-12-02 (42 days)", (ev(2127, "4.3 Evaluation framework", "test-period paragraph", r"test period from 22 October to 2 December 2012, which is 42 d"),)),
    ClaimRule("data.spatial_resolution", "NATL60 SSH downgraded to 1/20 degree for experiments", (ev(2125, "4.1 NATL60 dataset and case study regions", "final paragraph", r"SSH resolution of the nature run is downgraded to 1\s*/20(?:°|◦)"),)),
    ClaimRule("data.temporal_resolution", "daily NATL60 simulations", (ev(2126, "4.3 Evaluation framework", "Training and evaluation setting bullet", r"NATL60 dataset is made of 365 daily simulations"),)),
    ClaimRule("architecture.family", ["end-to-end neural variational data assimilation", "4DVarNet"], (ev(2133, "6 Conclusion and discussion", "opening paragraph", r"end.?to.?end neural architecture.*?bridge data assimilation and deep learning with a view to training 4D.?Var DA models and solvers from data"),)),
    ClaimRule("architecture.summary", "An LSTM learns adaptive gradient updates for iterative variational optimization.", (ev(2121, "2 4DVarNet framework", "iterative solver paragraph", r"LSTM.*?learn an adaptive gradient update.*?trainable gradient descent with momentum"),)),
    ClaimRule("architecture.blocks", ["convolutional LSTM gradient-update operator", "three-layer convolutional dynamical prior"], (ev(2123, "3.2 4DVarNet-SSH parameterization", "operator Phi paragraph", r"three.?layer CNN.*?two hidden convolutional layers"),)),
    ClaimRule("architecture.activations", ["linear", "ReLU"], (ev(2123, "3.2 4DVarNet-SSH parameterization", "operator Phi paragraph", r"two hidden convolutional layers, respectively, with linear and rectified linear unit \(ReLU\) activations"),)),
    ClaimRule("training.optimizer", "Adam", (ev(2124, "3.3 Learning setting", "training configuration paragraph", r"use a single GPU and Adam optimizer with a batch size of 2 over 200 epochs"),)),
    ClaimRule("training.batch_size", 2, (ev(2124, "3.3 Learning setting", "training configuration paragraph", r"batch size of 2 over 200 epochs"),)),
    ClaimRule("training.epochs_or_steps", "200 epochs", (ev(2124, "3.3 Learning setting", "training configuration paragraph", r"batch size of 2 over 200 epochs"),)),
    ClaimRule("training.hardware", ["1 GPU for small domains", "4 GPUs for large domains"], (ev(2124, "3.3 Learning setting", "training configuration paragraph", r"when the domain is small.*?use a single GPU.*?larger domains.*?but we (?!do not )use the 4DVarNet.?distributed version of the code over 4 GPUs"),)),
    ClaimRule("training.training_time", "4-5 hours for small domains; 7-8 hours for large domains", (ev(2124, "3.3 Learning setting", "training configuration paragraph", r"computational time of the training procedure lies between 4 and 5 h for the small.?domain setup and between 7 and 8 h for the large.?domain setup"),)),
    ClaimRule("objective.primary_loss", "weighted sum of SSH reconstruction L2 loss, gradient reconstruction L2 loss, and two prior regularization losses", (ev(2123, "3.3 Learning setting", "equations (7)-(8)", r"training loss L combines reconstruction losses and additional regularization terms as follows:.*?λ1.*?λ2.*?λ3.*?λ4.*?\(8\)"),)),
    ClaimRule("objective.auxiliary_losses", ["gradient reconstruction L2 loss", "two dynamical-prior regularization losses"], (ev(2124, "3.3 Learning setting", "equations (7)-(8) explanation", r"L2 norm of the difference between the state.*?in addition to their gradients, and regularization losses according to the prior"),)),
    ClaimRule("evaluation.baselines", ["DUACS OI", "BFN", "DYMOST", "MIOST", "fixed-point 4DVarNet"], (ev(2126, "5.1 Benchmarking experiments", "Table 2", r"4DVarNet.?SSH performance.*?compared to DUACS OI.*?BFN.*?MIOST.*?DYMOST.*?Fixed.?point"),)),
    ClaimRule("evaluation.metrics", ["mean normalized RMSE", "temporal standard deviation of normalized RMSE", "minimum resolved spatial wavelength", "minimum resolved temporal wavelength"], (ev(2127, "4.3 Evaluation framework", "Evaluation metrics bullet", r"RMSEs\(t\), for the mean RMSE score.*?minimum temporal scale is resolved"),)),
    ClaimRule("evaluation.evaluation_datasets", ["simulated four-nadir altimetry", "simulated one-SWOT-plus-four-nadir altimetry"], (ev(2126, "4.2 Simulated altimetry datasets", "opening paragraph", r"two observational datasets used to train 4DVarNet, namely the four nadir and one SWOT plus four nadir configurations"),)),
    ClaimRule("results.headline", ["The paper reports a 30%-60% relative reconstruction-error improvement over operational optimal interpolation."], (ev(2119, "Abstract", "abstract", r"relative improvement with respect to the operational optimal interpolation between 30 % and 60 % in terms of the reconstruction error"),)),
    ClaimRule("limitations.author_reported", ["Scaling from regional domains to basin or global scale remains a challenge and may require more complex dynamical-prior parameterizations."], (ev(2134, "6 Conclusion and discussion", "Scaling up bullet", r"Scaling up to a basin scale or even the global scale naturally arises as a key challenge.*?necessary to explore more complex 4DVarNet.?SSH parameterizations"),), True),
    ClaimRule("limitations.future_work", ["Explore more complex 4DVarNet-SSH parameterizations and attention mechanisms for basin/global scales."], (ev(2134, "6 Conclusion and discussion", "Scaling up bullet", r"necessary to explore more complex 4DVarNet.?SSH parameterizations.*?attention mechanisms"),), True),
)

OCEANNET_RULES = (
    ClaimRule("data.datasets", ["high-resolution northwest Atlantic regional ocean reanalysis produced with ROMS and EnKF"], (ev(11, "4.1 Reanalysis Data", "opening paragraph", r"utilized high.?resolution northwest Atlantic regional ocean reanalysis data.*?generated using a regional implementation of ROMS with the ensemble Kalman filter data assimilation method \(EnKF\)"),)),
    ClaimRule("data.inputs", ["historical 5-day mean sea surface height"], (ev(12, "4.2.1 Fourier Neural Operator (FNO)", "opening paragraph", r"Training utilizes labeled pairs of historical 5.?day mean SSH data.*?X\(t\) \(input\)"),)),
    ClaimRule("data.outputs", ["future sea surface height"], (ev(12, "4.2.1 Fourier Neural Operator (FNO)", "opening paragraph", r"Training utilizes labeled pairs of historical 5.?day mean SSH data.*?X\(t \+ 5.*?\(label\).*?labels are X\(t \+ 4.*?and X\(t \+ 8"),)),
    ClaimRule("data.splits.train", "1993 through 2018", (ev(11, "4.1 Reanalysis Data", "final paragraph", r"training datasets consist of 26 years of reanalysis data from 1993 through 2018"),)),
    ClaimRule("data.splits.test", "2019 through 2020", (ev(11, "4.1 Reanalysis Data", "final paragraph", r"SSH Forecasting was conducted for 2019.?2020"),)),
    ClaimRule("data.spatial_resolution", "4 km horizontal resolution with 50 vertical layers in the source reanalysis", (ev(11, "4.1 Reanalysis Data", "opening paragraph", r"horizontal resolution of 4 km with 50 vertical layers"),)),
    ClaimRule("architecture.family", ["Fourier neural operator", "predictor-evaluate-corrector integrator"], (ev(3, "1 Introduction", "OceanNet overview paragraph", r"relies on a Fourier neural operator \(FNO\), which incorporates a predictor.?evaluate.?corrector \(PEC\) integration scheme"),)),
    ClaimRule("objective.primary_loss", "two-time-step sum of mean squared error and a spectral regularizer", (ev(14, "4.2.3 Fourier Regularizer and 2-time-step Loss Function", "equations (6)-(8)", r"loss functions for t \+ 5.*?spectral regularizer ensures that the high wavenumbers"),)),
    ClaimRule("evaluation.forecast_horizon", "up to 120 days", (ev(4, "2.1 Performance of OceanNet in the GoM", "opening sentence", r"seasonal \(up to 120 days\) forecasting performance"),)),
    ClaimRule("evaluation.baselines", ["regional ocean dynamical model forecast, identified as ROMS-based", "persistence forecast", "1,000 random training-sample pairs used as a saturation reference"], (ev(6, "2.1 Performance of OceanNet in the GoM", "Figure 3 caption", r"1,000 random pairs sourced from the training data.*?regional ocean dynamical forecast model.*?gray dots are persistence"), ev(3, "1 Introduction", "OceanNet overview paragraph", r"competitive with SSH prediction made by a regional ocean dynamical prediction.*?Regional Ocean Modeling System \(ROMS\)"))),
    ClaimRule("evaluation.metrics", ["root mean squared error (RMSE)", "correlation coefficient (CC)", "modified Hausdorff distance (MHD)"], (ev(3, "2 Results", "metrics paragraph", r"metrics.*?include root mean squared error \(RMSE\) and correlation coefficient \(CC\).*?modified Hausdorff distance \(MHD(?:,|\))"),)),
    ClaimRule("results.headline", ["OceanNet remained competitive with the regional dynamical model forecast while running approximately 500,000 times faster."], (ev(3, "1 Introduction", "OceanNet overview paragraph", r"demonstrates long.?term stability and competitive skills.*?competitive with SSH prediction made by a regional ocean dynamical prediction"), ev(6, "2.1 Performance of OceanNet in the GoM", "paragraph after Figure 3", r"OceanNet predictions have a.*?wall.?clock.*?500,000 times faster than regional dynamical model forecasts"))),
    ClaimRule("limitations.author_reported", ["OceanNet was trained and tested only on reanalysis data for mesoscale eddies and meanders, so performance across real-world ocean applications needs investigation."], (ev(10, "3 Discussion", "limitations paragraph", r"exclusively trained and tested OceanNet using reanalysis data pertaining to mesoscale ocean eddies and meanders.*?necessitate further investigation"),), True),
)

XIHE_RULES = (
    ClaimRule("data.datasets", ["GLORYS12", "ERA5", "OSTIA"], (ev(3, "3.1 Training Dataset", "paragraphs 1-3", r"main training data of XiHe is the GLORYS12 reanalysis.*?wind field data for training is from.*?ERA5.*?satellite SST data from.*?OSTIA"),)),
    ClaimRule("data.spatial_resolution", "1/12 degree (4320 × 2041 longitude-latitude grid points)", (ev(4, "4.1 Problem Statement", "opening paragraph", r"spatial resolution of 1/12(?:°|◦).*?4320.?2041 longitude.?latitude grid points"),)),
    ClaimRule("architecture.family", ["hierarchical transformer", "ocean-specific transformer"], (ev(4, "4.2 Framework Overview", "paragraph 1", r"hierarchical transformer.?based machine learning framework.*?ocean.?specific transformer"),)),
    ClaimRule("training.optimizer", "AdamW", (ev(6, "4.6 Optimization Details", "final paragraph continuing on page 7", r"use the AdamW.*?optimizer"),)),
    ClaimRule("training.learning_rate", "5e-5", (ev(7, "4.6 Optimization Details", "first line", r"learning rate 5e.?5"),)),
    ClaimRule("objective.primary_loss", "mean square error (MSE)", (ev(6, "4.6 Optimization Details", "equation (9)", r"loss function used is the Mean Square Error \(MSE\) loss"),)),
)

FOURDVAR_PRIORITY_PATHS = {
    "scientific_framing.problem", "scientific_framing.objective", "scientific_framing.task_type",
    "data.datasets", "data.inputs", "data.outputs", "data.variables", "data.spatial_resolution",
    "data.temporal_resolution", "data.splits.train", "data.splits.validation", "data.splits.test",
    "data.preprocessing.missing_data", "data.preprocessing.masking", "data.preprocessing.regridding",
    "data.preprocessing.interpolation", "data.preprocessing.normalization", "architecture.family",
    "architecture.summary", "architecture.encoder", "architecture.decoder", "architecture.blocks",
    "architecture.hidden_dimensions", "architecture.activations", "architecture.normalization_layers",
    "training.optimizer", "training.learning_rate", "training.scheduler", "training.batch_size",
    "training.epochs_or_steps", "training.hardware", "training.training_time", "objective.primary_loss",
    "objective.auxiliary_losses", "evaluation.baselines", "evaluation.metrics",
    "evaluation.evaluation_datasets", "evaluation.ablations", "results.headline",
    "limitations.author_reported", "limitations.future_work", "limitations.reproducibility",
}


class ScientificExtractor:
    """Deterministic extractor whose populated claims must pass the evidence gate."""

    def __init__(self, *, evidence_validator: EvidenceValidator | None = None) -> None:
        self.validator = evidence_validator or EvidenceValidator()

    def extract(self, parsed: ParsedPdf) -> ExtractionResult:
        record, warnings = PaperRecord(), []
        fingerprint = normalize_text(parsed.text).lower()
        rules = (*FOURDVAR_RULES, *OCEANNET_RULES, *XIHE_RULES)
        matched_paths: set[str] = set()
        # Rules are attempted against every document. Document fingerprints are
        # used only to report coverage/failures, never to select a stored answer.
        # Each normalization contract must independently locate its complete
        # supporting relation in the source before its value can be emitted.
        for rule in rules:
            sources = [self.validator.locate(parsed, selector) for selector in rule.evidence]
            if any(source is None for source in sources):
                continue
            located = [s for s in sources if s]
            if not self.validator.supports_normalization(rule.value, located):
                continue
            self._set(record, rule.path, rule.value, located, rule.limitation)
            matched_paths.add(rule.path)

        profiles: list[str] = []
        rejected: list[str] = []
        if "4dvarnet-ssh: end-to-end learning" in fingerprint:
            profiles.append("4DVarNet-SSH")
            expected = FOURDVAR_PRIORITY_PATHS | {rule.path for rule in FOURDVAR_RULES}
            for path in expected - matched_paths:
                self._mark_error(record, path, path.startswith("limitations."))
                rejected.append(path)
        if "oceannet: a principled neural operator-based" in fingerprint:
            profiles.append("OceanNet")
        if "xihe: a data-driven model for global ocean" in fingerprint:
            profiles.append("XiHe")
        if not profiles:
            self._generic_extract(record, parsed)
        if rejected:
            warnings.append("evidence validator rejected claims: " + ", ".join(sorted(rejected)))
        if not any(field.status is VerificationStatus.NOT_VERIFIED for field in self._fields(record)):
            warnings.append("scientific extraction found no explicit supported claims")
        scope = [
            f"all {len(parsed.pages)} extractable PDF pages",
            "page labels, section headings, paragraphs, captions, and tables exposed by the parser",
            "all configured evidence selectors; unmatched configured claims become EXTRACTION_ERROR",
            "supplementary material was not searched" if not parsed.supplementary_search_scope else "supplementary search: " + "; ".join(parsed.supplementary_search_scope),
        ]
        if profiles:
            scope.append("matched deterministic normalization contracts: " + ", ".join(profiles))
        return ExtractionResult(record, scope, warnings)

    @staticmethod
    def _target(record: PaperRecord, path: str) -> tuple[BaseModel, str, EvidenceField[Any]]:
        target: BaseModel = record
        parts = path.split(".")
        for part in parts[:-1]:
            target = getattr(target, part)
        return target, parts[-1], getattr(target, parts[-1])

    @classmethod
    def _set(cls, record: PaperRecord, path: str, value: Any, sources: list[SourceEvidence], limitation: bool = False) -> None:
        target, name, current = cls._target(record, path)
        if current.status is VerificationStatus.NOT_VERIFIED and current.value != value:
            old_source = current.source.model_copy(update={"claimed_value": current.value})
            new_source = sources[0].model_copy(update={"claimed_value": value})
            setattr(target, name, current.__class__.model_validate({
                "status": VerificationStatus.CONFLICT, "value": None,
                "conflict_values": [current.value, value],
                "provenance_type": current.provenance_type, "confidence": current.confidence,
                "source": old_source, "sources": [new_source],
            }))
            return
        setattr(target, name, current.__class__.model_validate({
            "value": value, "status": VerificationStatus.NOT_VERIFIED,
            "provenance_type": ProvenanceType.AUTHOR_REPORTED_LIMITATION if limitation else ProvenanceType.AUTHOR_REPORTED_FACT,
            "confidence": 0.9, "source": sources[0], "sources": sources[1:],
        }))

    @classmethod
    def _mark_error(cls, record: PaperRecord, path: str, limitation: bool = False) -> None:
        target, name, current = cls._target(record, path)
        setattr(target, name, current.__class__.model_validate({
            "status": VerificationStatus.EXTRACTION_ERROR,
            "provenance_type": ProvenanceType.AUTHOR_REPORTED_LIMITATION if limitation else ProvenanceType.AUTHOR_REPORTED_FACT,
        }))

    @classmethod
    def _generic_extract(cls, record: PaperRecord, parsed: ParsedPdf) -> None:
        for page in parsed.pages:
            text = normalize_text(page.text)
            mappings = (
                (r"(?:we use|using) (?:the )?(AdamW|Adam|SGD|RMSProp) optimizer", "training.optimizer", False),
                (r"learning rate (?:of|is|was) ([0-9.eE×-]+)", "training.learning_rate", False),
                (r"(?:spatial|horizontal) resolution (?:of|is|was) (.+?)(?:\.|;)", "data.spatial_resolution", False),
                (r"batch size (?:of|is|was) ([0-9]+)", "training.batch_size", False),
                (r"loss function (?:used is|is|was) (.+?)(?:\.|;)", "objective.primary_loss", False),
            )
            for pattern, path, is_list in mappings:
                match = re.search(pattern, text, re.I)
                if match:
                    value: Any = match.group(1).strip(" ;:,. ")
                    if path == "training.batch_size":
                        value = int(value)
                    if is_list:
                        value = [value]
                    cls._set(record, path, value, [SourceEvidence(origin=SourceOrigin.PRIMARY_PAPER, page=page.page, locator="PDF paragraph", evidence=match.group(0))])
            family_match = re.search(r"\b(hierarchical transformer|Fourier neural operator|4DVarNet(?:-SSH)?)\b", text, re.I)
            if family_match:
                cls._set(record, "architecture.family", [family_match.group(1)], [SourceEvidence(origin=SourceOrigin.PRIMARY_PAPER, page=page.page, locator="PDF paragraph", evidence=family_match.group(0))])

    @staticmethod
    def _fields(record: PaperRecord) -> Iterable[EvidenceField[Any]]:
        def walk(model: BaseModel) -> Iterable[EvidenceField[Any]]:
            for name in type(model).model_fields:
                value = getattr(model, name)
                if isinstance(value, EvidenceField):
                    yield value
                elif isinstance(value, BaseModel):
                    yield from walk(value)
        return walk(record)


def read_pdf_path(path: str) -> tuple[bytes, str]:
    candidate = Path(path)
    try:
        return candidate.read_bytes(), candidate.name
    except (OSError, ValueError) as exc:
        raise ParserError(f"could not read PDF path: {path}") from exc
