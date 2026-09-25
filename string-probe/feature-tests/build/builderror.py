from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from compiler_provenance.parsing.superc import SuperC
from compiler_provenance.parsing.presence_condition import PresenceCondition


@dataclass(frozen=True)
class BuildErrorLocation:
    file: str
    line: int
    presence_conditions: list[PresenceCondition] 


class BuildErrorPresenceExtractor:
    ERROR_RE = re.compile(
        r"^(?P<file>[^:\s][^:]*):"
        r"(?P<line>\d+)"
        r"(?::(?P<col>\d+))?:\s*"
        r"(?P<kind>fatal error|error):\s*"
        r"(?P<msg>.*)$"
    )

    def __init__(self, source_root: str | Path):
        self.source_root = Path(source_root)
        

    def parse_log_text(self, log_text: str, library_dir: str) -> list[BuildErrorLocation]:
        results: list[BuildErrorLocation] = []

        for raw_line in log_text.splitlines():
            line = raw_line.rstrip()

            match = self.ERROR_RE.match(line)
            if not match:
                continue
            print("Matched Error line", match)
            file_name = match.group("file")
            line_no = int(match.group("line"))

            col = match.group("col")
            column = int(col) if col is not None else None

            resolved = self.resolve_source_file(file_name)

            presence_conditions = None
            print("Resolver", resolved)
            if resolved is not None:
                try:
                    print("Running SuperC for error line")
                    superc = SuperC()
                    print("SuperC instance created")
                    presence_conditions = superc.get_pc_and_macro_values(str(resolved), library_dir=library_dir, line_number=line_no)
                    print("Presence conditions for error:", presence_conditions)
                    results.append(
                    BuildErrorLocation(
                        file=file_name,
                        line=line_no,
                        presence_conditions=presence_conditions,
                    ))
                    return results
                except Exception as e:
                    presence_conditions = f"<superc failed: {e}>"
                    print("SuperC failed for error line:", e)

            results.append(
                BuildErrorLocation(
                    file=file_name,
                    line=line_no,
                    presence_conditions=presence_conditions,
                )
            )


        return results

    def parse_log_file(self, log_path: str | Path, library_dir: str) -> list[BuildErrorLocation]:
        log_path = Path(log_path)
        return self.parse_log_text(log_path.read_text(errors="ignore"), library_dir=library_dir)

    def resolve_source_file(self, file_name: str) -> Path | None:
        direct = self.source_root / file_name

        if direct.exists():
            return direct

        matches = list(self.source_root.rglob(Path(file_name).name))

        if not matches:
            return None

        wanted_parts = Path(file_name).parts

        for match in matches:
            if match.parts[-len(wanted_parts):] == wanted_parts:
                return match

        return matches[0]