#!/usr/local/bin/python
"""Container entry point; leaves the research implementations unchanged."""
import ast
import importlib
import json
import os
from pathlib import Path
import random
import runpy
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(os.environ.get("ARTIFACT_ROOT", "/opt/artifact"))
WORKSPACE = Path("/workspaces/RevEng")
MODULES = ("scripts.run_demo", "scripts.run_demo_opt", "scripts.run_demo_opt_os")


def initialize():
    from layout import create_layout
    create_layout(ROOT, WORKSPACE, Path("/results"))


def projects_for(module):
    """Read the upstream main block's project list without running experiments."""
    from core.project import Project
    path = ROOT / "string-probe/feature-tests" / (module.replace(".", "/") + ".py")
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.If) and "__name__" in ast.unparse(node.test):
            for statement in node.body:
                if isinstance(statement, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "projects" for t in statement.targets
                ):
                    return eval(compile(ast.Expression(statement.value), str(path), "eval"),
                                {"Path": Path, "Project": Project})
    raise RuntimeError(f"No projects list in {path}")


def doctor(module):
    if module not in MODULES:
        raise ValueError(f"Choose one of {MODULES}")
    failures = []
    for name in ("compiler_provenance.flag_recovery", "build.buildroot", module):
        try:
            importlib.import_module(name)
        except Exception as exc:
            failures.append(f"Import {name}: {exc}")
    try:
        from compiler_provenance.parsing.superc import SuperC
        SuperC()
    except Exception as exc:
        failures.append(f"SuperC: {exc}")
    try:
        projects = projects_for(module)
    except Exception as exc:
        failures.append(f"Project configuration: {exc}")
        projects = []
    for project in projects:
        required = [project.source_dir, project.include_dir,
                    project.build_dir / ".config", project.build_dir / "Makefile",
                    project.metadata["binary"], project.metadata["config_h"],
                    WORKSPACE / "header/libraries" / (project.name + ".h"),
                    WORKSPACE / "header/other_defines" / ("other_defines_" + project.name + ".h"),
                    WORKSPACE / (project.name + "_stripped_strings.txt")]
        if project.metadata.get("include"):
            required.append(Path(project.metadata["include"]))
        for path in required:
            if not Path(path).exists():
                failures.append(f"{project.name}: missing {path}")
        strings = WORKSPACE / (project.name + "_stripped_strings.txt")
        if strings.exists() and not strings.read_text().strip():
            failures.append(f"{project.name}: target strings file is empty: {strings}")
        makefile = project.build_dir / "package" / project.name / (project.name + ".mk")
        if not makefile.is_file():
            failures.append(f"Missing {makefile}")
        elif project.name != "libopenssl" and f"apply_{project.name}_truth.sh" not in makefile.read_text():
            failures.append(f"Missing custom post-configure truth hook in {makefile}")
    if module in ("scripts.run_demo_opt", "scripts.run_demo_opt_os"):
        variant = "buildroot-opt" if module.endswith("_opt") else "buildroot-opt-Os"
        for project in projects:
            for original in (project.metadata["binary"], project.metadata["config_h"]):
                path = WORKSPACE / variant / original.relative_to(project.build_dir)
                if not path.is_file():
                    failures.append(f"Missing optimization input {path}")
            logdir = ROOT / "string-probe/feature-tests/logs" / project.name
            if not logdir.is_dir() or not any(p.is_file() for p in logdir.iterdir()):
                failures.append(f"{project.name}: optimization replay needs standard-run logs (new or existing) and their referenced bundles in {logdir}")
    host = WORKSPACE / "buildroot-2025.02.4/output/host"
    for path in (host / "bin/gcc-13.real", host / "bin/arm-buildroot-linux-gnueabihf-strip"):
        if not os.access(path, os.X_OK):
            failures.append(f"Missing executable {path}")
    include = host / "lib/gcc/arm-buildroot-linux-gnueabihf/13.3.0/include"
    if not include.is_dir():
        failures.append(f"Missing compiler include directory {include}")
    if failures:
        print("Experiment prerequisites are incomplete:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 2
    print(f"Ready to run {module}.")
    return 0


def main():
    args = sys.argv[1:] or ["help"]
    command = args.pop(0)
    if command in ("help", "--help", "-h"):
        print("""Paper artifact commands:
  layout                      Create all writable directories (safe to repeat)
  prepare [--sources-only]    Install matching Buildroot trees; compile unless sources-only
  smoke                       Compile a C fixture, test Python integration and SuperC
  doctor [MODULE]             Check paper experiment inputs (default scripts.run_demo)
  run [MODULE]                Check inputs, then run the upstream experiment
  bash                        Open a shell in /results
  COMMAND [ARGS...]           Run an explicit command in the container

Modules: scripts.run_demo, scripts.run_demo_opt, scripts.run_demo_opt_os
Run prepare to reconstruct the matching Buildroot inputs.
See README.md for source locations, run commands, and required inputs.""")
        return 0
    if command == "prepare":
        from prepare import main as prepare_main
        return prepare_main(ROOT, args)
    if command == "layout":
        import argparse
        from layout import create_layout
        parser = argparse.ArgumentParser()
        parser.add_argument("--workspace", type=Path, default=WORKSPACE)
        parser.add_argument("--results", type=Path, default=Path("/results"))
        options = parser.parse_args(args)
        create_layout(ROOT, options.workspace.resolve(), options.results.resolve())
        print("Workspace and result directories created; existing files preserved.")
        return 0
    initialize()
    if command == "smoke":
        runpy.run_path(str(ROOT / "artifact/smoke.py"), run_name="__main__")
        return 0
    if command in ("doctor", "run"):
        module = args.pop(0) if args else MODULES[0]
        if args:
            raise ValueError("Unexpected arguments: " + " ".join(args))
        status = doctor(module)
        if status or command == "doctor":
            return status
        seed = int(os.environ.get("ARTIFACT_SEED", "0"))
        random.seed(seed)
        Path("/results/run-metadata.json").write_text(json.dumps({
            "module": module, "seed": seed, "sources": json.loads((ROOT / "sources.lock.json").read_text()),
            "python": sys.version,
        }, indent=2) + "\n")
        # Keep the upstream multiprocessing behavior. Its worker random state
        # is not made reproducible merely by seeding the parent process.
        sys.argv = [module]
        runpy.run_module(module, run_name="__main__")
        return 0
    os.execvp(command, [command, *args])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"artifact: {exc}", file=sys.stderr)
        sys.exit(2)
