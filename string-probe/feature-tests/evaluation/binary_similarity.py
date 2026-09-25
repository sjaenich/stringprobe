from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BinarySimilarityResult:
    similarity_percent: float
    confidence_percent: float | None
    output: str

    @property
    def similarity(self) -> float:
        """Similarity normalized to the range 0.0–1.0."""
        return self.similarity_percent / 100.0

    @property
    def confidence(self) -> float | None:
        """Confidence normalized to the range 0.0–1.0."""
        if self.confidence_percent is None:
            return None
        return self.confidence_percent / 100.0


class BinarySimilarityCalculator:
    RESULT_RE = re.compile(
        r"^\s*Similarity:\s*"
        r"(?P<similarity>\d+(?:\.\d+)?)%"
        r"(?:\s*\(Confidence:\s*"
        r"(?P<confidence>\d+(?:\.\d+)?)%\))?",
        re.MULTILINE,
    )

    SEPARATE_CONFIDENCE_RE = re.compile(
        r"^\s*Confidence:\s*(\d+(?:\.\d+)?)%",
        re.MULTILINE,
    )

    def __init__(
        self,
        script_path: str | Path,
        *,
        timeout: float | None = None,
        show_progress: bool = True,
    ):
        self.script_path = Path(script_path).expanduser().resolve()
        self.timeout = timeout
        self.show_progress = show_progress

    def calculate(
        self,
        primary_binary: str | Path,
        secondary_binary: str | Path,
    ) -> BinarySimilarityResult:
        if not self.script_path.is_file():
            raise FileNotFoundError(
                f"Similarity script not found: {self.script_path}"
            )

        primary = self._validate_binary(primary_binary, "primary")
        secondary = self._validate_binary(secondary_binary, "secondary")
    
        
                       
        command = [
            "bash",
            str(self.script_path),
            str(primary),
            str(secondary),
        ]

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            output_lines: list[str] = []

            assert process.stdout is not None

            for line in process.stdout:
                output_lines.append(line)

                if self.show_progress:
                    print(line, end="", flush=True)

            try:
                return_code = process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

                raise TimeoutError(
                    f"Similarity calculation exceeded "
                    f"{self.timeout} seconds"
                )

        except OSError as error:
            raise RuntimeError(
                f"Could not execute {self.script_path}: {error}"
            ) from error

        output = "".join(output_lines)
        result = self._parse_result(output)

        if result is not None:
            similarity, confidence = result

            return BinarySimilarityResult(
                similarity_percent=similarity,
                confidence_percent=confidence,
                output=output,
            )

        if return_code != 0:
            raise RuntimeError(
                f"Similarity script exited with status {return_code}.\n"
                f"Output:\n{output}"
            )

        raise RuntimeError(
            "The script completed but did not print a similarity value.\n"
            f"Output:\n{output}"
        )

    def _parse_result(
        self,
        output: str,
    ) -> tuple[float, float | None] | None:
        matches = list(self.RESULT_RE.finditer(output))

        if not matches:
            return None

        match = matches[-1]

        similarity = float(match.group("similarity"))
        confidence_text = match.group("confidence")

        if confidence_text is not None:
            confidence = float(confidence_text)
        else:
            confidence_matches = list(
                self.SEPARATE_CONFIDENCE_RE.finditer(output)
            )
            confidence = (
                float(confidence_matches[-1].group(1))
                if confidence_matches
                else None
            )

        return similarity, confidence

    @staticmethod
    def _validate_binary(
        binary_path: str | Path,
        description: str,
    ) -> Path:
        path = Path(binary_path).expanduser().resolve()

        if not path.is_file():
            raise FileNotFoundError(
                f"{description.capitalize()} binary not found: {path}"
            )

        return path