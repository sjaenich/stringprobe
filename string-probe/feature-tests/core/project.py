from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from compiler_provenance.flag_recovery import FlagRecovery
from build.builderror import BuildErrorLocation

@dataclass
class Project:
    name: str
    source_dir: Path
    build_dir: Path
    include_dir: Path
    metadata: dict | None = None


@dataclass
class BuildResult:
    success: bool
    log_file: Path
    binary_paths: list[Path]
    error: BuildErrorLocation


@dataclass
class RecoveryResult:
    flags: set[str]
    raw_output: Path
    runtime_sec: float
    frr: FlagRecovery

@dataclass
class ComparisonResult:
    precision: float
    recall: float
    f1: float
    tp: set[str]
    fp: set[str]
    fn: set[str]


@dataclass
class ExperimentResult:
    project: str
    build_success: bool
    config_found: bool
    precision: Optional[float]
    recall: Optional[float]
    f1: Optional[float]
    notes: str = ""