"""Demonstrate the real-world fact checker against live public registries.

Runs the :class:`warden.runtime.fact_checker.FactChecker` against a
mixture of real and fabricated facts so you can see the verdict for
each with your own eyes. No model calls are made; this is purely a
grounding-layer demo.
"""

from __future__ import annotations

import json

from warden.runtime.fact_checker import FactChecker


SAMPLE = """
The crash is reproducible on pypi: numpy 2.3.0 and pypi: requests 2.31.0.
Note: the allegedly related pypi: zorkyfluxcapacitor 9.9.9 does NOT exist.
The root cause appears related to CVE-2021-44228 (Log4Shell) but NOT to
CVE-2099-99999 which is fictional.
Docs: https://pypi.org/project/requests/ and also https://warden-fake-docs.invalid/none.
""".strip()


def main() -> None:
    checker = FactChecker()
    try:
        report = checker.check_text(SAMPLE)
    finally:
        checker.close()
    print(json.dumps(report.to_dict(), indent=2))


if __name__ == "__main__":  # pragma: no cover
    main()
