import subprocess
import time
from pathlib import Path

from core.project import Project, BuildResult


class AutotoolsBuildManager:
    def build(self, project: Project) -> BuildResult:
        log_file = project.build_dir / "build.log"
        project.build_dir.mkdir(parents=True, exist_ok=True)

        def run(cmd, cwd):
            with log_file.open("a") as f:
                return subprocess.run(
                    cmd,
                    cwd=cwd,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    check=False,
                )

        start = time.time()

        run(["autoreconf", "-fi"], project.source_dir)

        res_cfg = run(
            ["./configure", f"--prefix={project.build_dir / 'install'}"],
            project.source_dir,
        )
        if res_cfg.returncode != 0:
            return BuildResult(False, log_file, [])

        res_make = run(["make", "-j"], project.source_dir)
        success = res_make.returncode == 0

        binaries = list(project.source_dir.rglob("*"))
        binaries = [p for p in binaries if p.is_file() and p.stat().st_mode & 0o111]

        return BuildResult(success, log_file, binaries)
