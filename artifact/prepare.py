"""Reconstruct Buildroot trees from pinned upstream releases and observed paths."""
import argparse
import ast
import contextlib
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile

from layout import MODULES, TREES, VERSIONS, catalog, create_layout

BASE = "buildroot-2025.02.4"
WORKSPACE = Path("/workspaces/RevEng")


def hook_block(package, workspace):
    variable = package.upper() + "_POST_CONFIGURE_HOOK"
    hook = workspace / "support" / f"apply_{package}_truth.sh"
    block = (f"\n# Paper artifact post-configure truth hook.\n"
             f"define {variable}\n\t{hook} $(@D)\nendef\n\n"
             "ifneq ($(ARTIFACT_BOOTSTRAP),1)\n")
    # OpenSSL's upstream manager modifies Configure arguments and writes no
    # apply script. Register this hook if the author supplies one later.
    if package == "libopenssl":
        block += f"ifneq ($(wildcard {hook}),)\n"
    block += f"{package.upper()}_POST_CONFIGURE_HOOKS += {variable}\n"
    if package == "libopenssl":
        block += "endif\n"
    return block + "endif\n\n"


def required_packages(tree_name):
    return [name for name in VERSIONS
            if name != "libxml2" or tree_name in ("buildroot-2025.copy", "buildroot-opt-Os")]


def render_config(root, workspace, tree_name):
    # Preserve the supplied input byte-for-byte; transform only the runtime copy.
    config = (root / "configs/baseline.config").read_text()
    edits = {"BR2_DL_DIR": f'"{workspace}/downloads"'}
    if tree_name in ("buildroot-opt", "buildroot-opt-Os"):
        for choice in ("0", "1", "2", "3", "G", "S", "FAST"):
            edits["BR2_OPTIMIZE_" + choice] = "n"
        edits["BR2_OPTIMIZE_" + ("0" if tree_name == "buildroot-opt" else "S")] = "y"
    if tree_name in ("buildroot-2025.copy", "buildroot-opt-Os"):
        edits["BR2_PACKAGE_LIBXML2"] = "y"
    for key, value in edits.items():
        line = f"# {key} is not set" if value == "n" else f"{key}={value}"
        pattern = rf"^(?:{re.escape(key)}=.*|# {re.escape(key)} is not set)$"
        config, count = re.subn(pattern, lambda _: line, config, flags=re.MULTILINE)
        if not count:
            config += line + "\n"
    return config


def verify_archives(root):
    lock = json.loads((root / "downloads/sources.lock.json").read_text())
    for source in lock:
        path = root / "downloads" / source["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise RuntimeError(f"Checksum mismatch: {path}")
    return {source["file"]: source for source in lock}


def prepare_sources(root, workspace):
    lock = verify_archives(root)
    for name, optimization in TREES.items():
        tree = workspace / name
        marker = tree / ".artifact-source.json"
        spec = {"archive": lock[BASE + ".tar.xz"], "curl": lock["curl-7.71.1.tar.xz"],
                "optimization": optimization, "recipe_revision": 2}
        if marker.exists():
            if json.loads(marker.read_text()) != spec:
                raise RuntimeError(f"Existing managed source differs: {tree}; use a fresh workspace")
            continue
        if (tree / "Makefile").exists() or any(p.name != "output" for p in tree.iterdir()):
            raise RuntimeError(f"Refusing to overwrite an unmanaged Buildroot tree: {tree}")
        with tempfile.TemporaryDirectory(dir=workspace, prefix=".extract-") as tmp:
            with tarfile.open(root / "downloads" / (BASE + ".tar.xz")) as archive:
                # The pinned Buildroot archive intentionally includes absolute target-rootfs
                # symlinks. tar_filter still confines extracted member paths to tmp.
                archive.extractall(tmp, filter="tar")
            shutil.copytree(Path(tmp) / BASE, tree, dirs_exist_ok=True, symlinks=True)
        curl = tree / "package/libcurl/libcurl.mk"
        content = curl.read_text().replace("LIBCURL_VERSION = 8.14.1", "LIBCURL_VERSION = 7.71.1")
        if "LIBCURL_VERSION = 7.71.1" not in content:
            raise RuntimeError("Unexpected Buildroot curl recipe")
        curl.write_text(content)
        (curl.parent / "libcurl.hash").write_text(
            "# Archived HTTPS downloads; hashes recorded by artifact setup.\n"
            f"sha256  {lock['curl-7.71.1.tar.xz']['sha256']}  curl-7.71.1.tar.xz\n"
            f"sha256  {(root / 'downloads/curl-COPYING.sha256').read_text().strip()}  COPYING\n")
        for package in VERSIONS:
            path = tree / "package" / package / (package + ".mk")
            text = path.read_text()
            anchor = "$(eval $(generic-package))" if package == "libopenssl" else "$(eval $(autotools-package))"
            if anchor not in text:
                raise RuntimeError(f"Unexpected build system in {path}")
            path.write_text(text.replace(anchor, hook_block(package, workspace) + anchor, 1))
        marker.write_text(json.dumps(spec, indent=2) + "\n")
    cache = workspace / "downloads/libcurl"
    cache.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "downloads/curl-7.71.1.tar.xz", cache / "curl-7.71.1.tar.xz")


def build_plan(root, module):
    selection = catalog(root)
    modules = MODULES if module == "all" else (module,)
    plan = {BASE: set()}
    for selected in modules:
        for project in selection[selected]:
            tree = project["build_dir"].name
            plan.setdefault(tree, set()).add(project["name"])
            if selected in ("scripts.run_demo_opt", "scripts.run_demo_opt_os"):
                variant = "buildroot-opt" if selected.endswith("_opt") else "buildroot-opt-Os"
                plan.setdefault(variant, set()).add(project["name"])
    return plan, [(module, p) for module in modules for p in selection[module]]


def run_logged(command, logfile, env):
    print("Running:", " ".join(map(str, command)), "-- log:", logfile, flush=True)
    with logfile.open("a") as out:
        subprocess.run(command, check=True, stdout=out, stderr=subprocess.STDOUT, env=env)


def configure(root, workspace, tree, env):
    config = render_config(root, workspace, tree.name)
    requested = tree / ".artifact-defconfig"
    if requested.exists() and requested.read_text() != config:
        raise RuntimeError(f"Configuration changed for {tree}; rebuild in a fresh workspace")
    requested.write_text(config)
    log = workspace / "bootstrap-logs" / (tree.name + ".log")
    if not (tree / ".config").exists():
        run_logged(["make", "-C", tree, f"BR2_DEFCONFIG={requested}", "defconfig"], log, env)
    # Confirm normalization did not silently drop essential Kconfig choices.
    normalized = (tree / ".config").read_text()
    for setting in ('BR2_arm=y', 'BR2_ARM_EABIHF=y', 'BR2_GCC_VERSION="13.3.0"',
                    'BR2_TOOLCHAIN_BUILDROOT_GLIBC=y'):
        if setting not in normalized.splitlines():
            raise RuntimeError(f"Missing required setting {setting} in {tree}/.config")
    for package in required_packages(tree.name):
        if f"BR2_PACKAGE_{package.upper()}=y" not in normalized.splitlines():
            raise RuntimeError(f"Kconfig disabled {package} in {tree}/.config")
    variables = ["GNU_TARGET_NAME", "GCC_VERSION"] + [name.upper() + "_VERSION" for name in required_packages(tree.name)]
    output = subprocess.check_output(["make", "--no-print-directory", "-s", "-C", str(tree),
                                      "printvars", "VARS=" + " ".join(variables)], env=env, text=True)
    actual = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    expected = {"GNU_TARGET_NAME": "arm-buildroot-linux-gnueabihf", "GCC_VERSION": "13.3.0"}
    expected.update({name.upper() + "_VERSION": version for name, version in VERSIONS.items() if name in required_packages(tree.name)})
    for variable, value in expected.items():
        if actual.get(variable) != value:
            raise RuntimeError(f"{tree}: expected {variable}={value}, got {actual.get(variable)}")
    (tree / ".artifact-versions.json").write_text(json.dumps(actual, indent=2) + "\n")
    return log


def compatibility_compiler(workspace):
    bindir = workspace / BASE / "output/host/bin"
    compiler = bindir / "arm-buildroot-linux-gnueabihf-gcc"
    if not compiler.is_file():
        raise RuntimeError(f"Expected ARM compiler missing: {compiler}")
    # Current active ground-truth classes return no MY_EXTRA_FLAGS. This shim
    # gives the upstream manager's path a real target compiler, without guessing
    # the author's original wrapper or renaming Buildroot's own wrappers.
    (bindir / "gcc-13.real").write_text(
        '#!/bin/sh\nexec "$(dirname "$0")/arm-buildroot-linux-gnueabihf-gcc" "$@"\n')
    (bindir / "gcc-13.real").chmod(0o755)


def seed_inputs(root, workspace, selected):
    module = importlib.import_module("scripts.run_demo")
    source = root / "string-probe/feature-tests/scripts/run_demo.py"
    assignment = next(node for node in ast.walk(ast.parse(source.read_text()))
                      if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "groundtruth_map" for t in node.targets))
    truth_classes = eval(compile(ast.Expression(assignment.value), str(source), "eval"), vars(module))
    seen = set()
    for _, project in selected:
        name = project["name"]
        key = (str(project["build_dir"]), name)
        if key in seen:
            continue
        seen.add(key)
        metadata = project["metadata"]
        for keyname in ("binary", "config_h"):
            if not metadata[keyname].is_file():
                raise RuntimeError(f"Built {name}, but expected path is missing: {metadata[keyname]}")
        snapshot = workspace / "support/header-seeds" / (name + ".h")
        shutil.copy2(metadata["config_h"], snapshot)
        output = workspace / (name + "_stripped_strings.txt")
        if not output.exists():
            with output.open("w") as out:
                subprocess.run(["strings", "-n3", str(metadata["binary"])], stdout=out, check=True)
        free = workspace / "header/libraries" / (name + ".h")
        fixed = workspace / "header/other_defines" / ("other_defines_" + name + ".h")
        if not free.exists() or not fixed.exists():
            with (workspace / "bootstrap-logs" / (name + "-headers.log")).open("a") as log, contextlib.redirect_stdout(log):
                truth_classes[name]().extract(snapshot, name, project["source_dir"])
        if not free.is_file() or not fixed.is_file():
            raise RuntimeError(f"Upstream extractor did not create the expected headers for {name}")


def main(root, argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", choices=(*MODULES, "all"), default=MODULES[0])
    parser.add_argument("--sources-only", action="store_true", help="Extract all five trees and install package recipes; do not compile")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--workspace", type=Path, default=WORKSPACE, help="Alternate path allowed only with --sources-only")
    parser.add_argument("--results", type=Path, default=Path("/results"))
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    workspace = args.workspace.resolve()
    if not args.sources_only and (platform.system() != "Linux" or workspace != WORKSPACE):
        parser.error("Compilation must run in the Linux container at /workspaces/RevEng")
    create_layout(root, workspace, args.results.resolve())
    prepare_sources(root, workspace)
    plan, selected = build_plan(root, args.module)
    print(json.dumps({tree: sorted(packages) for tree, packages in plan.items()}, indent=2))
    if args.sources_only:
        print("Sources and directories prepared. Toolchain, benchmark binaries and generated headers are not built yet.")
        return 0
    env = os.environ.copy()
    env.pop("MY_REAL_COMPILER", None)
    env.pop("MY_EXTRA_FLAGS", None)
    env["SOURCE_DATE_EPOCH"] = "1704067200"
    env["ARTIFACT_BOOTSTRAP"] = "1"
    for name, packages in plan.items():
        tree = workspace / name
        log = configure(root, workspace, tree, env)
        # Explicit package targets avoid building a kernel/rootfs image.
        run_logged(["make", "-C", tree, f"-j{args.jobs}", "toolchain"], log, env)
        if name == BASE:
            compatibility_compiler(workspace)
        for package in sorted(packages):
            run_logged(["make", "-C", tree, f"-j{args.jobs}", package], log, env)
    seed_inputs(root, workspace, selected)
    print("Buildroot inputs prepared. Run artifact doctor before starting experiments.")
    return 0
