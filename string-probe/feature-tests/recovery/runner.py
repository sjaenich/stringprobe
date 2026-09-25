import subprocess
import time
from pathlib import Path
from compiler_provenance.flag_recovery import FlagRecovery
from core.project import Project, RecoveryResult


class FlagRecoveryRunner:
    def __init__(self):
        self.binary_strings = None
        self.source_code_strings = None
        self.frr = None
        

    def run(self, project: Project, binary: Path, config_h,stage, iteration: int) -> RecoveryResult:
        output_file = project.build_dir / "recovery.txt"
        start = time.time()
        extra_include = project.metadata["include"]
        if iteration == 1:
            print("Initialization of FlagRecovery")
            self.frr = FlagRecovery(project.source_dir, binary, config_h, project.name, project.include_dir, extra_include)
            self.frr.run(stage)

        print("Running only macro recovery")
        macros = self.frr.run_only_macros()

        self.binary_strings = self.frr.binary_strings
        self.source_code_strings = self.frr.SourceStrings

        runtime = time.time() - start       
   
        return RecoveryResult(macros, output_file, runtime, self.frr)





