"""Measure how the valuation engine sits relative to observed asking prices.

Usage (from apps/api, with the virtual environment active):

    python -m echte_auto_waarde.evaluate_market
    python -m echte_auto_waarde.evaluate_market --source-key import:dealer-example
    python -m echte_auto_waarde.evaluate_market --make BMW --model "3 Serie" --output report.json

Every eligible listing is valued against every other listing but itself, and the
estimate is compared with the asking price that was actually observed for it.

**This is not an accuracy measurement.** An asking price is what somebody was
asking, not what a car sold for and not what it was worth. What is reported is
deviation from observed asking prices: a coherence check on the model, never a
score against ground truth.

Only imported real evidence takes part. Synthetic demo listings are excluded
whatever the configured market mode is, nothing is fetched, and no valuation is
stored: consumer history is untouched by a run.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path

from echte_auto_waarde.db.session import SessionLocal
from echte_auto_waarde.domain.evaluation import (
    DEFAULT_OUTLIER_COUNT,
    MIN_SEGMENT_SIZE,
    DeviationMetrics,
    EvaluationReport,
)
from echte_auto_waarde.services.evaluation import EvaluationFilters, evaluate_market

logger = logging.getLogger("echte_auto_waarde.evaluate_market")


def _euro(cents: int | None) -> str:
    if cents is None:
        return "-"
    return "EUR " + f"{cents / 100:,.0f}".replace(",", ".")


def _percent(ratio: float | None) -> str:
    return "-" if ratio is None else f"{ratio * 100:.1f}%"


def _signed_percent(ratio: float | None) -> str:
    return "-" if ratio is None else f"{ratio * 100:+.1f}%"


def _print_metrics(metrics: DeviationMetrics, indent: str = "  ") -> None:
    logger.info("%sevaluated listings      : %d", indent, metrics.evaluated_count)
    logger.info("%sinsufficient evidence   : %d", indent, metrics.insufficient_evidence_count)
    logger.info(
        "%smedian abs deviation    : %s (%s)",
        indent,
        _euro(metrics.median_absolute_deviation_cents),
        _percent(metrics.median_absolute_deviation_ratio),
    )
    logger.info(
        "%sP75 abs deviation       : %s", indent, _percent(metrics.p75_absolute_deviation_ratio)
    )
    logger.info(
        "%sP90 abs deviation       : %s", indent, _percent(metrics.p90_absolute_deviation_ratio)
    )
    logger.info(
        "%smean signed deviation   : %s",
        indent,
        _signed_percent(metrics.mean_signed_deviation_ratio),
    )
    logger.info(
        "%sestimated above / below : %s / %s",
        indent,
        _percent(metrics.share_estimated_above_ask),
        _percent(metrics.share_estimated_below_ask),
    )


def print_report(report: EvaluationReport) -> None:
    logger.info("Deviation from observed asking prices - %s", report.dataset)
    logger.info("(asking prices are observations: not sale prices, not ground truth)")
    logger.info("")
    _print_metrics(report.overall)

    for name, segments in report.segments.items():
        logger.info("")
        logger.info("%s (groups of at least %d):", name, report.minimum_segment_size)
        for segment in segments:
            logger.info(
                "  %-24s n=%-4d median %-7s P90 %-7s bias %s",
                segment.label,
                segment.metrics.evaluated_count,
                _percent(segment.metrics.median_absolute_deviation_ratio),
                _percent(segment.metrics.p90_absolute_deviation_ratio),
                _signed_percent(segment.metrics.mean_signed_deviation_ratio),
            )

    directional = report.confidence_is_directionally_sound
    logger.info("")
    logger.info("Confidence diagnostic:")
    if directional is None:
        logger.info("  not enough confidence bands to say anything.")
    elif directional:
        logger.info("  higher-confidence valuations deviate no more than low-confidence ones.")
    else:
        logger.info(
            "  higher-confidence valuations deviate MORE than low-confidence ones. "
            "Worth investigating before trusting the score; nothing is changed here."
        )

    if report.outliers:
        logger.info("")
        logger.info("Largest deviations (diagnosis, not exclusions):")
        for item in report.outliers:
            logger.info(
                "  %-16s %s %s %s -> est %s, ask %s (%s), n=%d, confidence %s",
                item.external_reference,
                item.make,
                item.model,
                item.year or "?",
                _euro(item.estimated_market_value_cents),
                _euro(item.observed_asking_price_cents),
                _signed_percent(item.deviation_ratio),
                item.comparable_count,
                _percent(item.confidence_score),
            )
            if item.adjustments:
                logger.info(
                    "      adjustments: %s",
                    ", ".join(f"{kind} {_euro(amount)}" for kind, amount in item.adjustments),
                )
            if item.comparable_references:
                logger.info("      evidence: %s", ", ".join(item.comparable_references[:8]))


def _metrics_dict(metrics: DeviationMetrics) -> dict[str, object]:
    return {
        "evaluatedCount": metrics.evaluated_count,
        "insufficientEvidenceCount": metrics.insufficient_evidence_count,
        "medianAbsoluteDeviationCents": metrics.median_absolute_deviation_cents,
        "medianAbsoluteDeviationRatio": metrics.median_absolute_deviation_ratio,
        "p75AbsoluteDeviationRatio": metrics.p75_absolute_deviation_ratio,
        "p90AbsoluteDeviationRatio": metrics.p90_absolute_deviation_ratio,
        "meanSignedDeviationRatio": metrics.mean_signed_deviation_ratio,
        "shareEstimatedAboveAsk": metrics.share_estimated_above_ask,
        "shareEstimatedBelowAsk": metrics.share_estimated_below_ask,
    }


def write_json(report: EvaluationReport, path: Path) -> None:
    payload = {
        "measurement": ("deviation from observed asking prices; not accuracy against sale prices"),
        "dataset": report.dataset,
        "listingCount": report.listing_count,
        "overall": _metrics_dict(report.overall),
        "segments": {
            name: [
                {"label": segment.label, **_metrics_dict(segment.metrics)} for segment in segments
            ]
            for name, segments in report.segments.items()
        },
        "largestDeviations": [
            {
                "externalReference": item.external_reference,
                "make": item.make,
                "model": item.model,
                "year": item.year,
                "observedAskingPriceCents": item.observed_asking_price_cents,
                "estimatedMarketValueCents": item.estimated_market_value_cents,
                "deviationRatio": item.deviation_ratio,
                "comparableCount": item.comparable_count,
                "confidenceScore": item.confidence_score,
                "comparableReferences": list(item.comparable_references),
                "adjustments": [
                    {"type": kind, "amountCents": amount} for kind, amount in item.adjustments
                ],
            }
            for item in report.outliers
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(report: EvaluationReport, path: Path) -> None:
    """One row per reported group, for a spreadsheet."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "segment",
                "group",
                "evaluated",
                "insufficient_evidence",
                "median_abs_deviation_ratio",
                "p75_abs_deviation_ratio",
                "p90_abs_deviation_ratio",
                "mean_signed_deviation_ratio",
            ]
        )
        rows = [("overall", report.dataset, report.overall)]
        rows += [
            (name, segment.label, segment.metrics)
            for name, segments in report.segments.items()
            for segment in segments
        ]
        for name, label, metrics in rows:
            writer.writerow(
                [
                    name,
                    label,
                    metrics.evaluated_count,
                    metrics.insufficient_evidence_count,
                    metrics.median_absolute_deviation_ratio,
                    metrics.p75_absolute_deviation_ratio,
                    metrics.p90_absolute_deviation_ratio,
                    metrics.mean_signed_deviation_ratio,
                ]
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure deviation between valuations and observed asking prices."
    )
    parser.add_argument("--source-key", help="Only evaluate listings from this data source.")
    parser.add_argument("--scope", help="Only evaluate listings imported under this scope.")
    parser.add_argument("--make")
    parser.add_argument("--model")
    parser.add_argument("--year-from", type=int)
    parser.add_argument("--year-to", type=int)
    parser.add_argument(
        "--min-group-size",
        type=int,
        default=MIN_SEGMENT_SIZE,
        help=f"Smallest group worth reporting (default {MIN_SEGMENT_SIZE}).",
    )
    parser.add_argument(
        "--outliers",
        type=int,
        default=DEFAULT_OUTLIER_COUNT,
        help=f"How many of the largest deviations to show (default {DEFAULT_OUTLIER_COUNT}).",
    )
    parser.add_argument("--output", type=Path, help="Write the report to a .json or .csv file.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    filters = EvaluationFilters(
        source_key=args.source_key,
        scope=args.scope,
        make=args.make,
        model=args.model,
        year_from=args.year_from,
        year_to=args.year_to,
    )

    with SessionLocal() as session:
        report = evaluate_market(
            session,
            filters,
            outlier_count=args.outliers,
            minimum_segment_size=args.min_group_size,
        )
        # Nothing is written, but roll back anyway so no stray flush from the
        # ORM identity map can ever reach the database from an evaluation.
        session.rollback()

    if report.listing_count == 0:
        logger.warning(
            "No imported listings matched. Import market data first with "
            "python -m echte_auto_waarde.import_market."
        )
        return 1

    print_report(report)

    if args.output:
        if args.output.suffix.lower() == ".csv":
            write_csv(report, args.output)
        else:
            write_json(report, args.output)
        logger.info("")
        logger.info("Report written to %s", args.output)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
