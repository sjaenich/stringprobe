#!/usr/bin/env python3

from __future__ import annotations
import os
import subprocess
from evaluation.binary_similarity import BinarySimilarityCalculator, BinarySimilarityResult
import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from evaluation.library_metrics_to_latex import (
    ProjectMetrics,
    count_binary_strings,
    count_source_strings,
    write_metrics_latex_table,
)



ITERATION_RE = re.compile(
    r"_(?P<number>\d+)(?:\.[^.]+)?$"
)

MACRO_VALUE_RE = re.compile(
    r"""["']?
        (?P<macro>[A-Z][A-Z0-9_]+)
        ["']?
        \s*(?:,|:|=)\s*
        ["']?
        (?P<value>True|False|true|false|1|0)
        ["']?
    """,
    re.VERBOSE,
)

DEFINE_RE = re.compile(
    r"^\s*#\s*define\s+"
    r"(?P<macro>[A-Z][A-Z0-9_]+)\b"
)

UNDEF_RE = re.compile(
    r"^\s*(?:"
    r"#\s*undef|"
    r"/\*\s*#\s*undef"
    r")\s+"
    r"(?P<macro>[A-Z][A-Z0-9_]+)\b"
)

BUNDLE_PATH_RE = re.compile(
    r"""(?P<path>
        /[^\s"'(),;:]*
        bundle
        [^\s"'(),;:]*
    )""",
    re.VERBOSE | re.IGNORECASE,
)

ITERATION_HEADER_RE = re.compile(
    r"^\s*=+\s*Iteration\s+(?P<number>\d+)\s*=+\s*$",
    re.IGNORECASE | re.MULTILINE,
)
class LibraryLogComparison:
    def __init__(
        self,
        library_name: str,
        logs_root: str | Path,
        similarity_script: str | Path,
        *,
        latex_output: str | Path | None =None, 
        binary_name: str | None = None,
        timeout: float | None = None,
        show_progress: bool = True,
    ):
        self.library_name = library_name
        self.binary_name = binary_name
        self.groundtruth_checks = {}
        self.logs_root = Path(logs_root).expanduser().resolve()
        self.logs_directory = self._resolve_logs_directory()
        latex_output = library_name + "_metrics_O0.tex"
        self.compare_groundtruth_script = Path(
    "/workspaces/RevEng/Tools/feature-tests/compare_ground_truth.sh"
).expanduser().resolve()
        self.metrics: list[ProjectMetrics] =[]

        self.latex_output = (
        Path(latex_output)
        .expanduser()
        .resolve()
        )
        self.similarity_calculator = BinarySimilarityCalculator(
            similarity_script,
            timeout=timeout,
            show_progress=show_progress,
        )

    @staticmethod
    def parse_groundtruth_comparison(
        output: str,
    ) -> dict:
        def get_text(pattern: str, field: str) -> str:
            match = re.search(
                pattern,
                output,
                flags=re.MULTILINE,
            )

            if not match:
                raise ValueError(
                    f"Could not parse {field!r} from "
                    f"compare_groundtruth.sh output:\n{output}"
                )

            return match.group(1).strip()

        def get_section(
            heading: str,
            next_heading: str | None,
        ) -> list[str]:
            if next_heading is None:
                pattern = (
                    rf"^\s*{re.escape(heading)}\s*:\s*$"
                    rf"(?P<body>.*)\Z"
                )
            else:
                pattern = (
                    rf"^\s*{re.escape(heading)}\s*:\s*$"
                    rf"(?P<body>.*?)"
                    rf"(?=^\s*{re.escape(next_heading)}\s*:\s*$)"
                )

            match = re.search(
                pattern,
                output,
                flags=re.MULTILINE | re.DOTALL,
            )

            if not match:
                return []

            return [
                line.strip()
                for line in match.group("body").splitlines()
                if line.strip() and line.strip() != "(none)"
            ]

        return {
            "file": get_text(
                r"^\s*File\s*:\s*(.+?)\s*$",
                "File",
            ),
            "project": get_text(
                r"^\s*Project\s*:\s*(.+?)\s*$",
                "Project",
            ),
            "first_iteration_flags": int(
                get_text(
                    r"^\s*First iteration flags\s*:\s*(\d+)\s*$",
                    "First iteration flags",
                )
            ),
            "last_iteration_flags": int(
                get_text(
                    r"^\s*Last iteration flags\s*:\s*(\d+)\s*$",
                    "Last iteration flags",
                )
            ),
            "exact_matches": int(
                get_text(
                    r"^\s*Exact matches\s*:\s*(\d+)\s*$",
                    "Exact matches",
                )
            ),
            "changed_flags": get_section(
                "Changed flags",
                "Only in first iteration",
            ),
            "only_in_first": get_section(
                "Only in first iteration",
                "Only in last iteration",
            ),
            "only_in_last": get_section(
                "Only in last iteration",
                None,
            ),
            "raw_output": output,
        }
    
    @staticmethod
    def split_iteration_sections(
        log_text: str,
    ) -> list[tuple[int, str]]:
        """
        Split a log into its internal iteration sections.

        Accepts headers such as:

            ===Iteration 1===
            ===== Iteration 2 =====
            ========== ITERATION 15 ==========

        Returns:

            [
                (1, "contents of iteration 1"),
                (2, "contents of iteration 2"),
            ]
        """
        matches = list(
            ITERATION_HEADER_RE.finditer(log_text)
        )

        sections: list[tuple[int, str]] = []

        for index, match in enumerate(matches):
            iteration_number = int(match.group("number"))
            section_start = match.end()

            if index + 1 < len(matches):
                section_end = matches[index + 1].start()
            else:
                section_end = len(log_text)

            section_text = log_text[
                section_start:section_end
            ].strip()

            sections.append(
                (iteration_number, section_text)
            )

        return sections







    def run(self) -> dict[Path, BinarySimilarityResult]:
        """
        Process every numbered log file independently.
        For each _N.log file:
        1. Find all "===== Iteration N =====" sections.
        2. Skip the file if it contains fewer than two sections.
        3. Read the ground-truth binary from the first section.
        4. Read the final macro configuration from the last section.
        5. Build the candidate binary.
        6. Invoke compare_groundtruth.sh through
        BinarySimilarityCalculator.
        7. Store the parsed similarity result.
        """
        iterations = self.discover_iterations()
        results: dict[Path, BinarySimilarityResult] = {}
        default_results: dict[Path, BinarySimilarityResult] = {}

        for file_number in sorted(iterations):
            paths = iterations[file_number]

            for log_path in sorted(paths):
                if not log_path.is_file():
                    print(f"[!] Skipping non-file: {log_path}")
                    continue

                print()
                print("=" * 72)
                print(f"Library:  {self.library_name}")
                print(f"Log file: {log_path}")
                print("=" * 72)

                log_text = log_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

                sections = self.split_iteration_sections(log_text)

                if len(sections) < 2:
                    print(
                        f"[*] Skipping {log_path.name}: found only "
                        f"{len(sections)} iteration section(s)"
                    )
                    continue

                first_iteration_number, first_iteration_text = sections[0]
                last_iteration_number, last_iteration_text = sections[-1]

                print(f"First internal iteration: {first_iteration_number}")
                print(f"Last internal iteration:  {last_iteration_number}")
                print(f"Internal iterations:      {len(sections)}")
                
                completed = subprocess.run(
                    [
                        "bash",
                        str(self.compare_groundtruth_script),
                        str(log_path),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )

                if completed.returncode != 0:
                    raise RuntimeError(
                        f"compare_groundtruth.sh failed for {log_path} "
                        f"with status {completed.returncode}:\n"
                        f"{completed.stdout}"
                    )

                parsed = self.parse_groundtruth_comparison(
                    completed.stdout
                )

                self.groundtruth_checks[log_path.resolve()] = parsed

                print(
                    f"{log_path.name}: "
                    f"{parsed['exact_matches']}/"
                    f"{parsed['first_iteration_flags']} exact matches"
                )

                try:
                    ground_truth_binary = self.find_ground_truth_binary(
                        first_iteration_text
                    )

                    macro_config = self.parse_macro_config(
                        last_iteration_text
                    )

                    print(f"Ground truth:  {ground_truth_binary}")
                    print(f"Macros parsed: {len(macro_config)}")


                    print("[*] Getting candidate binary...")

                    candidate_binary = ground_truth_binary.parent
                    candidate_binary = candidate_binary / "final_binary"


                    
                    

                    print(f"Candidate: {candidate_binary}")
                    print("[*] Invoking compare_groundtruth.sh...")
                    




                except Exception as error:
                    print(
                        f"[!] Failed to process {log_path.name}: {error}",
                        file=sys.stderr,
                    )
                    continue

                self.metrics.append(
                    ProjectMetrics(
                        project=parsed["project"],
                        correctly_recovered_flags=parsed["exact_matches"],
                        ground_truth_flags=parsed["first_iteration_flags"],
                        binary_strings=count_binary_strings(
                            candidate_binary
                        ),
                        source_strings=None,
                        iterations=len(sections),
                        binary_size_bytes=candidate_binary.stat().st_size,
                        default_binary_similarity_percent=(
                            0
                        ),
                        binary_similarity_percent=(
                            0
                        ),
                    )
                )



        print()
        print("Similarity summary")
        print("-" * 72)


        table_path = write_metrics_latex_table(
            self.metrics,
            self.latex_output,
        )
        print(f"[+] LaTeX table written to {table_path}")
        return results

    def _resolve_logs_directory(self) -> Path:
        candidates = [
            self.logs_root / self.library_name,
        ]

        if not self.library_name.startswith("lib"):
            candidates.append(
                self.logs_root / f"lib{self.library_name}"
            )

        for candidate in candidates:
            if candidate.is_dir():
                return candidate.resolve()

        raise NotADirectoryError(
            "Could not find the library log directory. Checked:\n"
            + "\n".join(f"  {path}" for path in candidates)
        )

    def discover_iterations(self) -> dict[int, list[Path]]:
        """
        Supports numbered files:

            library_0.log
            library_1.log
            library_2.log

        and numbered directories:

            library_0/
            library_1/
            library_2/
        """
        iterations: dict[int, list[Path]] = {}
        
        for path in self.logs_directory.iterdir():
            match = ITERATION_RE.search(path.name)
        
            if not match:
                continue

            number = int(match.group("number"))
            iterations.setdefault(number, []).append(path)

        if not iterations:
            raise RuntimeError(
                f"No numbered iterations found in "
                f"{self.logs_directory}. Expected names ending in "
                f"_0, _1, _2, etc."
            )

        return iterations

    @staticmethod
    def read_iteration(paths: list[Path]) -> str:
        parts: list[str] = []

        for path in sorted(paths):
            if path.is_file():
                parts.append(
                    path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    )
                )
                continue

            if not path.is_dir():
                continue

            for child in sorted(path.rglob("*")):
                if not child.is_file():
                    continue

                try:
                    parts.append(
                        child.read_text(
                            encoding="utf-8",
                            errors="replace",
                        )
                    )
                except OSError:
                    continue

        if not parts:
            raise RuntimeError(
                "No readable log content found in:\n"
                + "\n".join(f"  {path}" for path in paths)
            )

        return "\n".join(parts)



    def find_default_binary(self, candidate_binary):
        default_binary_dir = candidate_binary.parent.parent / f"{self.library_name}_default" 
        print("Default Binary Dir", default_binary_dir)
        if default_binary_dir.is_dir():
            for child in default_binary_dir.iterdir():
                return child

    def find_ground_truth_binary(
        self,
        log_text: str,
    ) -> Path:
        candidates: list[Path] = []
        referenced_but_missing: list[Path] = []

        matches = [m for m in BUNDLE_PATH_RE.finditer(log_text)]
        match = matches[0] if matches else None


        
        raw_path = match.group("path").rstrip(".]}")
        path = Path(raw_path).expanduser()
        directory = path.parent
        print(f"[*] Found referenced path: {directory}")
        if directory.is_dir():
            print(f"[*] Searching for ground-truth binary in {directory}")
            for child in directory.iterdir():
                if child.is_file() and "final" in child.name:
                    print(f"[*] Skipping final binary: {child}")
                elif child.is_file() and ".h" in child.name:
                    print(f"[*] Skipping header file: {child}")
                else:
                    resolved = child.resolve()
                    print(f"[*] Resolved ground-truth candidate: {resolved}")
                    if resolved not in candidates:
                        candidates.append(resolved)
                        
      

        if not candidates:
            message = (
                "No existing ground-truth binary with 'bundle' in its "
                "path was found in the first iteration."
            )

            if referenced_but_missing:
                message += "\nReferenced but missing paths:\n"
                message += "\n".join(
                    f"  {path}"
                    for path in referenced_but_missing[-10:]
                )

            raise FileNotFoundError(message)

        if self.binary_name:
            matching = [
                path
                for path in candidates
                if path.name == self.binary_name
                or self.binary_name in path.name
            ]

            if not matching:
                raise FileNotFoundError(
                    f"No ground-truth binary matching "
                    f"{self.binary_name!r} was found.\n"
                    f"Bundle candidates:\n"
                    + "\n".join(
                        f"  {path}" for path in candidates
                    )
                )

            candidates = matching

        else:
            shared_libraries = [
                path
                for path in candidates
                if ".so" in path.name
                or path.suffix in {".dylib", ".dll"}
            ]

            if shared_libraries:
                candidates = shared_libraries

        return candidates[-1]

    def find_ground_truth_config(
            self,
            log_text: str,
        ) -> Path:
            
            matches = [m for m in BUNDLE_PATH_RE.finditer(log_text)]
            match = matches[0] if matches else None
    

            raw_path = match.group("path").rstrip(".]}")
            path = Path(raw_path).expanduser()
            directory = path.parent
            print(f"[*] Found referenced path: {directory}")
            if directory.is_dir():
                print(f"[*] Searching for ground-truth binary in {directory}")
                for child in directory.iterdir():
                    if child.is_file() and ".h" in child.name:
                        print(f"[*] Skipping header file: {child}")
                        resolved = child.resolve()
                        print(f"[*] Resolved ground-truth candidate: {resolved}")
                        
            return resolved
                            
          


    @staticmethod
    def parse_macro_config(
        log_text: str,
    ) -> set[tuple[str, str]]:
        """
        Return macros in the format:

            {
                ("SOME_MACRO", "True"),
                ("OTHER_MACRO", "False"),
            }

        The log is processed in order. If a macro appears multiple times,
        its last value wins.
        """
        macros: dict[str, bool] = {}

        for line in log_text.splitlines():
            for match in MACRO_VALUE_RE.finditer(line):
                raw_value = match.group("value").lower()

                macros[match.group("macro")] = (
                    raw_value in {"true", "1"}
                )

            undef_match = UNDEF_RE.match(line)

            if undef_match:
                macros[undef_match.group("macro")] = False
                continue

            define_match = DEFINE_RE.match(line)

            if define_match:
                macros[define_match.group("macro")] = True

        if not macros:
            raise RuntimeError(
                "No macro configuration could be parsed from the "
                "last iteration."
            )

        return {
            (
                macro,
                "True" if enabled else "False",
            )
            for macro, enabled in macros.items()
        }



    def _extract_result_path(self, result: Any) -> Path:
        """
        Accept a direct path or a small selection of common result formats.
        """
        if isinstance(result, (str, Path)):
            return Path(result).expanduser()

        if isinstance(result, dict):
            keys = [
                "binary",
                "binary_path",
                "output_binary",
                "output_path",
            ]

            for key in keys:
                value = result.get(key)

                if value:
                    return Path(value).expanduser()

        attributes = [
            "binary",
            "binary_path",
            "output_binary",
            "output_path",
        ]

        for attribute in attributes:
            value = getattr(result, attribute, None)

            if value:
                return Path(value).expanduser()

        raise TypeError(
            "The Buildroot build method did not return a binary path. "
            "Update build_candidate() to obtain the generated binary "
            "from your Buildroot implementation."
        )




def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read a macro configuration from the final feature-test "
            "iteration, rebuild the library with Buildroot, and compare "
            "the result with the ground-truth binary from the first "
            "iteration."
        )
    )

    parser.add_argument(
        "library",
        help=(
            "Library/project name, for example libopenssl, libz, "
            "libcurl or libpng"
        ),
    )

    parser.add_argument(
        "--logs-root",
        default=(
            "/workspaces/RevEng/Tools/"
            "feature-tests/logs"
        ),
        help=(
            "Parent directory containing the library log directories"
        ),
    )

    parser.add_argument(
        "--binary-name",
        help=(
            "Expected binary filename. Use this when the project name "
            "and produced binary differ, for example "
            "'libopenssl --binary-name libcrypto.so'"
        ),
    )

    parser.add_argument(
        "--similarity-script",
        default="/workspaces/RevEng/support/binary_similarity.sh",
        help="Path to the Ghidra/BinDiff similarity shell script",
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=3600,
        help="Maximum similarity-calculation time in seconds",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not stream Ghidra and BinDiff progress",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    try:
        comparison = LibraryLogComparison(
            library_name=arguments.library,
            logs_root=arguments.logs_root,
            binary_name=arguments.binary_name,
            similarity_script=arguments.similarity_script,
            timeout=arguments.timeout,
            show_progress=not arguments.quiet,
        )

        result = comparison.run()

    except KeyboardInterrupt:
        print("\n[!] Interrupted", file=sys.stderr)
        return 130

    except Exception as error:
        print(f"[!] {error}", file=sys.stderr)
        return 1
        
    return 0


if __name__ == "__main__":
    raise SystemExit(main())