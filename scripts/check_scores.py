#!/usr/bin/env python3
"""Validate a score batch and select the best draft per author."""
import argparse
import json
import math
import sys

CAPS = {"hook": 20, "pain": 20, "clarity": 15, "credibility": 15,
        "rhythm": 15, "conversion": 15}
RUBRIC = "six-dimensions-5s-v1"


def check(batch, initial_six=False):
    if not isinstance(batch, dict):
        raise ValueError("Input must be one batch object")
    if batch.get("evaluator") not in ("codex", "doubao"):
        raise ValueError("evaluator must identify codex or doubao for the whole batch")
    if batch.get("rubric_version") != RUBRIC:
        raise ValueError("Unsupported rubric_version")
    if not isinstance(batch.get("round"), str) or not batch["round"].strip():
        raise ValueError("round must be a nonempty string")
    drafts = batch.get("drafts")
    if not isinstance(drafts, list) or not drafts:
        raise ValueError("drafts must be a nonempty list")
    seen, results = set(), []
    for d in drafts:
        if not isinstance(d, dict):
            raise ValueError("Each draft must be an object")
        ident = d.get("id")
        if not isinstance(ident, str) or not ident.strip() or ident in seen:
            raise ValueError("Each draft needs a unique nonempty id")
        seen.add(ident)
        if d.get("evaluator", batch["evaluator"]) != batch["evaluator"]:
            raise ValueError("Do not mix evaluators in a ranked batch")
        if d.get("rubric_version", RUBRIC) != RUBRIC:
            raise ValueError("Do not mix rubrics in a ranked batch")
        author = d.get("author")
        if author not in ("dsh", "gemini", "other"):
            raise ValueError(f"{ident}: author must be dsh, gemini or other")
        scores = d.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(CAPS):
            raise ValueError(f"{ident}: exactly six score keys required: {', '.join(CAPS)}")
        for key, cap in CAPS.items():
            n = scores[key]
            if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not 0 <= n <= cap:
                raise ValueError(f"{ident}: {key} must be a finite number from 0 to {cap}")
        total = round(sum(scores.values()), 6)
        if "total" in d:
            claimed = d["total"]
            if isinstance(claimed, bool) or not isinstance(claimed, (int, float)) or not math.isfinite(claimed) or not math.isclose(total, claimed, abs_tol=1e-6):
                raise ValueError(f"{ident}: supplied total does not equal six-score sum {total}")
        results.append({"id": ident, "author": author, "scores": scores, "total": total})
    if initial_six and (len(results) != 6 or any(sum(d["author"] == a for d in results) != 3 for a in ("dsh", "gemini"))):
        raise ValueError("Initial batch must contain exactly three DSH and three Gemini drafts")

    def order(d):
        s = d["scores"]
        return (-d["total"], -s["credibility"], -s["hook"], -s["rhythm"])

    ranked = sorted(results, key=order)
    for d in ranked:
        d["rank"] = 1 + sum(x["total"] > d["total"] for x in results)
    selections = {}
    for author in ("dsh", "gemini"):
        group = sorted((d for d in results if d["author"] == author), key=order)
        if group:
            best = group[0]
            selections[author] = {
                "selected": best["id"],
                "total_ties": [d["id"] for d in group if d["total"] == best["total"]],
                "unresolved_ties": [d["id"] for d in group if order(d) == order(best)],
            }
    return {"evaluator": batch["evaluator"], "round": batch["round"],
            "rubric_version": RUBRIC, "ranked": ranked, "per_author": selections}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-six", action="store_true")
    args = parser.parse_args()
    try:
        result = check(json.load(sys.stdin), args.initial_six)
    except (ValueError, TypeError) as exc:
        print(f"Invalid score batch: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
