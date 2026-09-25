"""Create writable output directories, without fabricating benchmark inputs."""
import ast
import json
from pathlib import Path

MODULES = ("scripts.run_demo", "scripts.run_demo_opt", "scripts.run_demo_opt_os")
TREES = {
    "buildroot-2025.02.4": "O2",
    "buildroot-2025.copy-optimization": "O2",
    "buildroot-2025.copy": "O2",
    "buildroot-opt": "O0",
    "buildroot-opt-Os": "Os",
}
VERSIONS = {
    "libcurl": "7.71.1", "dbus": "1.14.10", "dropbear": "2025.88",
    "expat": "2.7.1", "libpcap": "1.10.5", "nano": "8.2",
    "ncurses": "6.4-20230603", "pcre2": "10.44", "rsync": "3.4.1",
    "xz": "5.6.4", "libopenssl": "3.4.1", "libxml2": "2.13.8",
}


def catalog(root):
    result = {}
    for module in MODULES:
        path = root / "string-probe/feature-tests" / (module.replace(".", "/") + ".py")
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, ast.If) and "__name__" in ast.unparse(node.test):
                for statement in node.body:
                    if isinstance(statement, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "projects" for t in statement.targets
                    ):
                        result[module] = eval(compile(ast.Expression(statement.value), str(path), "eval"),
                                              {"Path": Path, "Project": lambda **kw: kw})
    if set(result) != set(MODULES):
        raise RuntimeError("Could not read all upstream project lists")
    return result


def create_layout(root, workspace, results, *, link_tools=True):
    workspace.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    projects = sorted(set(VERSIONS) | {p["name"] for entries in catalog(root).values() for p in entries})
    dirs = ["Tools", "support", "support/header-seeds", "header/libraries",
            "header/other_defines", "header/groundtruth", "all_strings", "superc_output",
            "string_diffs", "downloads", "bootstrap-logs"]
    dirs += [f"{tree}/output/build" for tree in TREES]
    dirs += [f"string_diffs/{project}" for project in projects]
    for directory in dirs:
        (workspace / directory).mkdir(parents=True, exist_ok=True)
    for log in ("logs", "logs-O0", "logs-O2", "logs-Os"):
        for project in projects:
            (results / log / project).mkdir(parents=True, exist_ok=True)
    if link_tools:
        for name in ("feature-tests", "compiler-provenance", "superc"):
            target = workspace / "Tools" / name
            expected = (root / "string-probe" / name).resolve()
            if target.is_symlink() and target.resolve() == expected:
                continue
            if target.exists() or target.is_symlink():
                raise RuntimeError(f"{target} already exists; use a fresh workspace or keep your original Tools elsewhere")
            target.symlink_to(expected, target_is_directory=True)
    # A useful, machine-readable record. Existing inputs are never truncated.
    report = {"workspace": str(workspace), "results": str(results), "buildroot_trees": TREES,
              "package_versions": VERSIONS, "projects": catalog(root)}
    (results / "layout.json").write_text(json.dumps(report, default=str, indent=2) + "\n")
    return report
