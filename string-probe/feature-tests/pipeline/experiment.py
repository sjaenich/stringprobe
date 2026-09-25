from core.project import ExperimentResult, Project
from pathlib import Path
from truth.config_truth import GroundTruthExtractor
import logging
import hashlib
import subprocess

def extract_strings_from_binary(binary_path: str) -> set[str]:
    try:
        result = subprocess.run(
            ["strings","-n3", binary_path],
            capture_output=True,
            text=True,
            check=True,
        )

        return set(result.stdout.splitlines())
        
        

    except subprocess.CalledProcessError:
        return set()
    
def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def load_strings(path: str) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    with open(p, "r", errors="ignore") as f:
        return {line.rstrip("\r\n") for line in f if line.strip()}

def append_new_strings(path: str, strings: set[str], iteration: int) -> int:
    p = Path(path)
    existing = load_strings(str(p))
    print(f"Existing strings in {p}: {len(existing)}, {existing}")
    
    new_strings = [s for s in strings if s not in existing]
    if iteration ==2 and len(new_strings) > 400:
        new_strings = new_strings[:400]
    print(f"New strings to add to {p}: {len(new_strings)}, {new_strings}")
    if new_strings:
        with open(p, "a") as f:
            for s in new_strings:
                f.write(s + "\n")

    return len(new_strings)

class ExperimentRunner:
    def __init__(
        self,
        build_manager,
        locator,
        recovery,
        truth_extractor,
        comparator,
    ):
        self.build_manager = build_manager
        self.locator = locator
        self.recovery = recovery
        self.truth_extractor = truth_extractor
        self.comparator = comparator


    def run_project_iteratively(self, project: Project, stage: str) -> ExperimentResult:
 
        
        config_h = project.metadata.get("config_h", None)

        if not config_h:
            return ExperimentResult(
                project.name, True, False, None, None, None, "config.h not found"
            )

        gt = self.truth_extractor.extract(config_h, project.name, project.source_dir)

        diff_dir = Path(f"/workspaces/RevEng/string_diffs/{project.name}")
        diff_dir.mkdir(parents=True, exist_ok=True)

        positive_path = diff_dir / "positive_strings.txt"
        negative_path = diff_dir / "negative_strings.txt"

        positive_path.unlink(missing_ok=True)
        negative_path.unlink(missing_ok=True)

        positive_path.touch()
        negative_path.touch()



        target_strings_path = f"/workspaces/RevEng/{project.name}_stripped_strings.txt"
        positive_path = f"/workspaces/RevEng/string_diffs/{project.name}/positive_strings.txt"
        negative_path = f"/workspaces/RevEng/string_diffs/{project.name}/negative_strings.txt"

        target_strings = load_strings(target_strings_path)

        if not target_strings:
            return ExperimentResult(
                project.name,
                True,
                False,
                None,
                None,
                None,
                "target binary strings not found",
            )

        last_binary_hash = None
        last_cmp_res = None
        last_rec = None
        iteration = 0

        while True:
            iteration += 1
            print(f"\n=== Iteration {iteration} ===")

            build_res = self.build_manager.build(project, self.truth_extractor, iteration)

            if iteration > 1 and not build_res.success:
                print("Build failed. Investigate macros")
                build_res.success = self.build_manager.rebuild_with_macros(project, self.truth_extractor, rec.frr, build_res)

            if not build_res.success:
                
                return ExperimentResult(
                    project.name, False, False, None, None, None, "build failed"
                )

            if not build_res.binary_paths:
                return ExperimentResult(
                    project.name, True, True, None, None, None, "no binaries"
                )

            compiled_binary = build_res.binary_paths[0]
            current_hash = file_hash(compiled_binary)

            if current_hash == last_binary_hash:
                print("No new binary produced. Stopping.")
                break

            last_binary_hash = current_hash

            if iteration == 1:
                recover_binary = build_res.binary_paths[1]
                added_negative = 0
                added_positive = 0

            if iteration > 1:
                self_compiled_strings = extract_strings_from_binary(compiled_binary)
                recreate_binary_strings = set(self.recovery.binary_strings)

                print("Self compiled strings:", len(self_compiled_strings), self_compiled_strings)
                print("Recreate binary strings:", len(recreate_binary_strings), recreate_binary_strings)
                negative_strings = self_compiled_strings - recreate_binary_strings
                positive_strings = recreate_binary_strings - self_compiled_strings

                added_negative = append_new_strings(negative_path, negative_strings, iteration)
                added_positive = append_new_strings(positive_path, positive_strings, iteration)

                print(f"Added {added_negative} negative strings")
                print(f"Added {added_positive} positive strings")




            rec = self.recovery.run(project, recover_binary, config_h, stage, iteration)
            last_rec = rec

            macros = set()
            ground_truth_single = set()
            for (m,_) in gt:
                ground_truth_single.add(m)
            print("Ground truth single:", ground_truth_single)

            for (m,b) in rec.flags:
                if m in ground_truth_single:
                    macros.add((m,b))
            print("Rec: ", macros)
            cmp_res = self.comparator.compare(rec.flags, gt)
            last_cmp_res = cmp_res


            self.truth_extractor.flags = macros
            self.truth_extractor.clean_conflicts()


            logger = logging.getLogger(project.name + "_telemetry")
            logger.info({
                "project": project.name,
                "iteration": iteration,
                "added_negative_strings": added_negative,
                "added_positive_strings": added_positive,
                "precision": cmp_res.precision,
                "recall": cmp_res.recall,
                "f1": cmp_res.f1,
                "binary_strings": len(self.recovery.binary_strings),
                "source_code_strings": len(self.recovery.source_code_strings),
                "number of Macros in GT": len(gt),
            })

            approach_logger = logging.getLogger(project.name + "_approach")
            approach_logger.info({
                "project": project.name,
                "iteration": iteration,
                "success": True,
                "precision": cmp_res.precision,
                "recall": cmp_res.recall,
                "f1": cmp_res.f1,
                "approach": rec.frr.approach,
            })

        if last_cmp_res is None:
            return ExperimentResult(
                project.name, True, False, None, None, None, "no iteration completed"
            )

        return ExperimentResult(
            project.name,
            True,
            True,
            last_cmp_res.precision,
            last_cmp_res.recall,
            last_cmp_res.f1,
        )