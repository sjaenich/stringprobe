from pathlib import Path
from core.project import Project


class ConfigLocator:
    CANDIDATES = [
        "config.h",
        "configuration.h",
        "confdef.h",
    ]

    def locate(self, project: Project, output_base: Path | None = None) -> Path | None:
        patterns = set(self.CANDIDATES)

        for name in self.CANDIDATES:
            patterns.add(f"*_{name}")
            patterns.add(f"*-{name}")
            patterns.add(f"*{name}")

        for root in [output_base]:
            print(f"Searching for config files in: {root}")
            for pattern in patterns:
                for p in root.rglob(pattern):
                    print(f"Checking candidate: {p}")
                    if p.is_file():
                        print(f"Located config file: {p}")
                        return p
        p = Path(project.metadata["config_h"])
        return None