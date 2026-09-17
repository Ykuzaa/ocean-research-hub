"""Command-line entry point for the extraction benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path

from ocean_research_hub.evaluation.benchmark import benchmark, load_golden
from ocean_research_hub.evaluation.models import PredictionSet


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark evidence-backed extraction predictions")
    parser.add_argument("predictions", type=Path)
    parser.add_argument(
        "--golden-dir", type=Path, default=Path("evaluation/golden_dataset")
    )
    args = parser.parse_args()
    predictions = PredictionSet.model_validate_json(
        args.predictions.read_text(encoding="utf-8")
    )
    report = benchmark(load_golden(args.golden_dir), predictions)
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
