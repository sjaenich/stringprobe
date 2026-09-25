"""Metric collection and LaTeX output for library comparisons."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SOURCE_TOKEN_RE = re.compile(
    r"""
    //[^\n]*
    |
    /\*.*?\*/
    |
    (?P<string>"(?:\\.|[^"\\])*")
    """,
    re.VERBOSE | re.DOTALL,
)

SOURCE_SUFFIXES = {
    ".c",
    ".h",
    ".cc",
    ".hh",
    ".cpp",
    ".hpp",
    ".cxx",
    ".hxx",
}


@dataclass(frozen=True)
class ProjectMetrics:
    """All values needed for one row of the results table."""

    project: str
    correctly_recovered_flags: int
    ground_truth_flags: int
    binary_strings: int
    source_strings: int
    iterations: int
    binary_size_bytes: int
    default_binary_similarity_percent: float
    binary_similarity_percent: float

    @property
    def recovered_flags_percent(self) -> float:
        """Percentage of ground-truth flags recovered exactly."""
        if self.ground_truth_flags == 0:
            return 100.0

        return (
            self.correctly_recovered_flags
            / self.ground_truth_flags
            * 100.0
        )

    @property
    def binary_size_kib(self) -> float:
        """Binary size expressed in kibibytes."""
        return self.binary_size_bytes / 1024.0

    @property
    def similarity_improvement_percentage_points(self) -> float:
        return (
            self.binary_similarity_percent - self.default_binary_similarity_percent
        )




def count_binary_strings(
    binary_path: str | Path,
    *,
    minimum_length: int = 4,
) -> int:
    """Count printable string occurrences reported by ``strings -a``."""
    binary = Path(binary_path).expanduser().resolve()

    if not binary.is_file():
        raise FileNotFoundError(f"Binary not found: {binary}")

    completed = subprocess.run(
        [
            "strings",
            "-a",
            "-n",
            str(minimum_length),
            str(binary),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"strings failed for {binary}:\n"
            f"{completed.stderr}"
        )

    return sum(
        1
        for line in completed.stdout.splitlines()
        if line.strip()
    )


def count_source_strings(
    source_directory: str | Path,
    *,
    suffixes: set[str] | None = None,
) -> int:
    """Count ordinary C/C++ string-literal occurrences in a source tree."""
    source_dir = Path(source_directory).expanduser().resolve()

    if not source_dir.is_dir():
        raise NotADirectoryError(
            f"Source directory not found: {source_dir}"
        )

    allowed_suffixes = suffixes or SOURCE_SUFFIXES
    count = 0

    for source_file in source_dir.rglob("*"):
        if (
            not source_file.is_file()
            or source_file.suffix.lower() not in allowed_suffixes
        ):
            continue

        try:
            source_text = source_file.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError as error:
            print(
                f"[!] Could not read {source_file}: {error}",
                file=sys.stderr,
            )
            continue

        count += sum(
            1
            for match in SOURCE_TOKEN_RE.finditer(source_text)
            if match.group("string") is not None
        )

    return count


def latex_escape(value: object) -> str:
    """Escape a value for use in a normal LaTeX table cell."""
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }

    return "".join(
        replacements.get(character, character)
        for character in str(value)
    )


def write_metrics_latex_table(
    metrics: Iterable[ProjectMetrics],
    output_path: str | Path,
    *,
    caption: str = (
        "Feature-recovery and binary-similarity results"
    ),
    label: str = "tab:feature-recovery-results",
) -> Path:
    """Write one LaTeX table row per :class:`ProjectMetrics` value."""
    records = sorted(
        metrics,
        key=lambda item: item.project.lower(),
    )

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        r"\begin{table*}[htbp]",
        r"\centering",
        rf"\caption{{{latex_escape(caption)}}}",
        rf"\label{{{label}}}",
        r"\small",
        r"\begin{tabular}{lrrrrrrrrrr}",
        r"\toprule",
        (
            r"Project & Correct & Ground truth & Recovery (\%) & "
            r"Binary strings & Source strings & Iterations & "
            r"Size (KiB) & Default sim. (\%) & Recovered sim. (\%) & "
            r"Improvement (pp) \\"
        ),
        r"\midrule",
    ]

    for item in records:
        lines.append(
            f"{latex_escape(item.project)} & "
            f"{item.correctly_recovered_flags} & "
            f"{item.ground_truth_flags} & "
            f"{item.recovered_flags_percent:.2f} & "
            f"{item.binary_strings} & "
            f"{item.source_strings} & "
            f"{item.iterations} & "
            f"{item.binary_size_kib:.2f} & "
            f"{item.default_binary_similarity_percent:.2f} & "
            f"{item.binary_similarity_percent:.2f} & "
            f"{item.similarity_improvement_percentage_points:+.2f} \\\\"
        )

    lines.extend(
        [
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table*}",
            "",
        ]
    )

    output.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return output

