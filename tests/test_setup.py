"""Portable checks: python -m unittest discover -s tests -v."""
import hashlib
import json
import runpy
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "artifact"))
from layout import TREES, VERSIONS, create_layout
from prepare import build_plan, verify_archives, render_config, hook_block


class SetupTests(unittest.TestCase):
    def test_log_replay_does_not_require_binary_comparison_tool(self):
        namespace = runpy.run_path(str(ROOT / "string-probe/feature-tests/evaluation/binary_similarity.py"))
        with tempfile.TemporaryDirectory() as tmp:
            calculator = namespace["BinarySimilarityCalculator"](Path(tmp) / "missing.sh")
            # Replay can construct the log reader without a comparison tool,
            # but an actual comparison must still report the missing tool.
            with self.assertRaisesRegex(FileNotFoundError, "Similarity script not found"):
                calculator.calculate("unused-primary", "unused-secondary")

    def test_author_config_and_explicit_overlays(self):
        original = (ROOT / "configs/baseline.config").read_text()
        def settings(text):
            return {line.split("=", 1)[0]: line.split("=", 1)[1]
                    for line in text.splitlines() if line.startswith("BR2_") and "=" in line}
        supplied = settings(original)
        for tree in TREES:
            actual = settings(render_config(ROOT, Path("/workspaces/RevEng"), tree))
            allowed = {"BR2_DL_DIR"}
            if tree in ("buildroot-opt", "buildroot-opt-Os"):
                allowed |= {key for key in set(actual) | set(supplied) if key.startswith("BR2_OPTIMIZE_")}
            if tree in ("buildroot-2025.copy", "buildroot-opt-Os"):
                allowed.add("BR2_PACKAGE_LIBXML2")
            changed = {key for key in set(actual) | set(supplied) if actual.get(key) != supplied.get(key)}
            self.assertLessEqual(changed, allowed)
            self.assertEqual(actual["BR2_cortex_a7"], "y")
            self.assertEqual(actual["BR2_ARM_FPU_VFPV4D16"], "y")
            self.assertEqual(actual["BR2_PACKAGE_NANO_TINY"], "y")
        self.assertEqual((ROOT / "configs/baseline.config").read_text(), original)

    def test_make_hook_receives_build_directory_and_skips_bootstrap(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "support").mkdir()
            package_dir = workspace / "nano-8.2"
            package_dir.mkdir()
            capture = workspace / "argument.txt"
            script = workspace / "support/apply_nano_truth.sh"
            script.write_text('#!/bin/sh\nprintf "%s\\n" "$1" > "' + str(capture) + '"\n')
            script.chmod(0o755)
            makefile = workspace / "Makefile"
            target = str(package_dir / ".stamp_configured")
            makefile.write_text(hook_block("nano", workspace) + f"\n.PHONY: {target}\n{target}:\n"
                                "\t$(foreach hook,$(NANO_POST_CONFIGURE_HOOKS),$(call $(hook)))\n\t@true\n")
            subprocess.run(["make", "-s", "-f", str(makefile), target], check=True)
            self.assertEqual(capture.read_text().strip(), str(package_dir))
            capture.unlink()
            subprocess.run(["make", "-s", "-f", str(makefile), "ARTIFACT_BOOTSTRAP=1", target], check=True)
            self.assertFalse(capture.exists())

    def test_layout_preserves_existing_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, results = Path(tmp) / "workspace", Path(tmp) / "results"
            create_layout(ROOT, workspace, results)
            sentinel = workspace / "header/libraries/nano.h"
            sentinel.write_text("original experiment input\n")
            create_layout(ROOT, workspace, results)
            self.assertEqual(sentinel.read_text(), "original experiment input\n")
            for tree in TREES:
                self.assertTrue((workspace / tree / "output/build").is_dir())
            for project in VERSIONS:
                self.assertTrue((workspace / "string_diffs" / project).is_dir())
                for log in ("logs", "logs-O0", "logs-O2", "logs-Os"):
                    self.assertTrue((results / log / project).is_dir())
            self.assertFalse((workspace / "nano_stripped_strings.txt").exists())
            self.assertEqual((workspace / "Tools/feature-tests").resolve(), ROOT / "string-probe/feature-tests")

    def test_existing_tools_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, results = Path(tmp) / "workspace", Path(tmp) / "results"
            original = workspace / "Tools/feature-tests"
            original.mkdir(parents=True)
            (original / "keep.txt").write_text("keep")
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                create_layout(ROOT, workspace, results)
            self.assertEqual((original / "keep.txt").read_text(), "keep")

    def test_real_download_checksums(self):
        self.assertEqual(len(verify_archives(ROOT)), 2)

    def test_plans_include_actual_optimization_targets(self):
        plan, projects = build_plan(ROOT, "all")
        self.assertEqual(set(plan), set(TREES))
        self.assertIn("libcurl", plan["buildroot-opt"])
        self.assertIn("libxml2", plan["buildroot-opt-Os"])
        self.assertIn("nano", plan["buildroot-2025.copy-optimization"])
        expected = set(VERSIONS) | {"flac", "tcpdump", "sqlite", "libxslt", "libssh2", "libvpx", "libarchive"}
        self.assertEqual({p["name"] for _, p in projects}, expected)
        for module in ("scripts.run_demo", "scripts.run_demo_opt", "scripts.run_demo_opt_os"):
            selected = [p for selected_module, p in projects if selected_module == module]
            self.assertEqual(len(selected), 21)
            self.assertEqual({p["name"] for p in selected}, expected)


if __name__ == "__main__":
    unittest.main()
