"""Run deterministic safety rules against the versioned deidentified dataset."""

import json
from pathlib import Path

import main


def run() -> None:
    cases = json.loads((Path(__file__).parent / "clinical_validation_cases.json").read_text(encoding="utf-8"))
    failures = []
    for case in cases:
        actual = main.check_red_flags(case["text"])
        if actual != case["expected_red_flag"]:
            failures.append(f"{case['id']}: expected {case['expected_red_flag']}, got {actual}")
    if failures:
        raise SystemExit("Clinical dataset failures:\n" + "\n".join(failures))
    print(f"Clinical dataset: {len(cases)}/{len(cases)} cases passed")


if __name__ == "__main__":
    run()
