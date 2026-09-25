"""Small integration test. This is not a reproduction of the paper evaluation."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

from compiler_provenance.flag_recovery import FlagRecovery
from compiler_provenance.parsing.string_parser import StringParser
from compiler_provenance.reverse_engineering.information.information_extractor import InformationExtractor
from evaluation.comparator import ResultComparator
from build.buildroot import BuildrootBuildManager
from z3 import Bool, Not, Solver, sat, unsat


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def smoke(python_only=False):
    with tempfile.TemporaryDirectory(prefix="artifact-smoke-") as directory:
        root = Path(directory)
        source = root / "fixture.c"
        binary = root / "fixture"
        source.write_text(
            'extern int puts(const char *);\n'
            'int main(void) {\n'
            '#ifdef FEATURE_HELLO\n'
            'return puts("artifact-feature-enabled");\n'
            '#else\n'
            'return puts("artifact-feature-disabled");\n'
            '#endif\n}\n'
        )
        subprocess.run(["cc", "-O0", "-DFEATURE_HELLO=1", str(source), "-o", str(binary)], check=True)
        parser = StringParser(source)
        parser.extract_string_literals()
        parser.clean_string_literals()
        strings = {entry.content for entry in parser.strings}
        require("artifact-feature-enabled" in strings and "artifact-feature-disabled" in strings,
                "Source parser did not find both branches")
        binary_strings = set(InformationExtractor(str(binary)).strings)
        require("artifact-feature-enabled" in binary_strings, "Enabled string missing from compiled binary")
        require("artifact-feature-disabled" not in binary_strings, "Disabled string present in compiled binary")
        if not python_only:
            from compiler_provenance.parsing.superc import SuperC
            header = root / "features.h"
            header.write_text("/* #undef FEATURE_HELLO */\n")
            workspace = Path("/workspaces/RevEng")
            name = root.name
            mock = workspace / "header/other_defines" / f"other_defines_{name}.h"
            mock.write_text("/* no fixed macros */\n")
            try:
                entries = SuperC().get_pc_and_macro_values(
                    source, str(root), 4, None, header, name, str(root), "")
                require(entries, "SuperC produced no presence conditions")
                solver = Solver()
                solver.add(entries[0].pc)
                require(solver.check() == sat, "Presence condition is unsatisfiable")
                solver.add(Not(Bool("FEATURE_HELLO")))
                require(solver.check() == unsat, "SuperC lost the feature guard")
            finally:
                mock.unlink(missing_ok=True)
                for path in (workspace / "superc_output").glob(f"output_{name}_*"):
                    path.unlink()
        result = ResultComparator().compare({("FEATURE_HELLO", "True")}, {("FEATURE_HELLO", "True")})
        require(result.precision == result.recall == result.f1 == 1.0, "Feature comparator failed")
        print(json.dumps({"status": "passed", "scope": "python-only" if python_only else "python-and-superc",
                          "source_strings": len(strings), "precision": result.precision}))


if __name__ == "__main__":
    smoke()
