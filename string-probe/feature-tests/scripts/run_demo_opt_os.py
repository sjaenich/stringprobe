from contextlib import redirect_stdout
import re
import glob
from .setup_logging import setup_logging
from pathlib import Path
from multiprocessing import Pool
import os
import shutil
from core.project import Project
from build.buildrootOptOs import BuildrootOptOs
from locate.config_locator import ConfigLocator
from recovery.runner import FlagRecoveryRunner
from truth.config_truth import GroundTruthExtractor
from evaluation.comparator import ResultComparator
from pipeline.experiment import ExperimentRunner
from truth.sqlite import SqliteGroundTruth
from truth.libvpx import LibvpxGroundTruth
from truth.alsalib import AlsaLibGroundTruth
from truth.rsync import RsyncGroundTruth
from truth.dbus import DbusGroundTruth
from truth.dropbear import DropbearGroundTruth
from truth.expat import ExpatGroundTruth
from truth.flac import FlacGroundTruth
from truth.libarchive import LibarchiveGroundTruth
from truth.libpcap import LibpcapGroundTruth
from truth.libssh2 import Libssh2GroundTruth
from truth.libxml2 import Libxml2GroundTruth
from truth.libxslt import LibxsltFeatureTruth
from truth.nano import NanoGroundTruth
from truth.ncurses import NcursesGroundTruth
from truth.pcre2 import Pcre2GroundTruth
from truth.xz import LiblzmaFeatureTruth
from truth.tcpdump import TcpdumpFeatureTruth
from truth.libcurl import LibcurlGroundTruth
from truth.libopenssl import OpensslGroundTruth
from scripts.run_comparison import LibraryLogComparison


BUNDLE_RE = re.compile(r"^(?P<project>.+)_(?P<ts>\d+(?:\.\d+)?)_bundle$")

def get_bundle_dirs_for_project(root_dir, project_name, n=3):
    """
    Glob-based version to get first n bundle dirs for a project.
    """
    root = Path(root_dir)

    pattern = f"{project_name}_*_bundle"

    matches = []

    for path in root.glob(pattern):
        if not path.is_dir():
            continue

        m = BUNDLE_RE.match(path.name)
        if not m:
            continue

        timestamp = float(m.group("ts"))
        matches.append((timestamp, path))

    matches.sort(key=lambda x: x[0])

    return [str(p) for _, p in matches[:n]]

def save_groundtruth_to_separate_file(project):
    config_h = f"/workspaces/RevEng/header/libraries/{project.name}.h"

    if not os.path.isfile(config_h):
        raise FileNotFoundError(f"{config_h} does not exist or is not a file")
    output_path = f"/workspaces/RevEng/header/groundtruth/{project.name}_groundtruth.h"
    if os.path.exists(output_path):
        return
    shutil.copy(str(config_h), output_path) 


def run_project_safe(project):
    setup_logging(project)
    try:
        result = run_project(project)
        return {
                "project": project.name,
                "status": "ok",
                "result": result,
        }   
    except Exception as e:
        import traceback
        traceback.print_exec()
        return {
            "project": project.name,
            "status": "error",
            "error": str(e),
        }



def run_project(project):
    

        
    groundtruth_map = {
        "libvpx": LibvpxGroundTruth,
        "rsync": RsyncGroundTruth,
        "alsa-lib": AlsaLibGroundTruth,
        "dbus": DbusGroundTruth,
        "dropbear": DropbearGroundTruth,
        "expat": ExpatGroundTruth,
        "flac": FlacGroundTruth,
        "libarchive": LibarchiveGroundTruth,
        "libpcap": LibpcapGroundTruth,
        "libssh2": Libssh2GroundTruth,
        "libxml2": Libxml2GroundTruth,
        "libxslt": LibxsltFeatureTruth,
        "nano": NanoGroundTruth,
        "ncurses": NcursesGroundTruth,
        "pcre2": Pcre2GroundTruth,
        "tcpdump": TcpdumpFeatureTruth,
        "xz": LiblzmaFeatureTruth,
        "libcurl": LibcurlGroundTruth,
        "sqlite": SqliteGroundTruth,
        "libopenssl": OpensslGroundTruth,
    }

    default_gt = GroundTruthExtractor

    gt_class = groundtruth_map.get(project.name.lower(), default_gt)
    truth_extractor = gt_class()
    opt_level="Os"
    
    log_dir = f"/workspaces/RevEng/Tools/feature-tests/logs-{opt_level}/{project.name}"
    os.makedirs(log_dir, exist_ok=True)

    seen_flags = set()
    collected = []

    run_id = 0
    accepted_id = 0


    comparison = LibraryLogComparison(
        logs_root="/workspaces/RevEng/Tools/feature-tests/logs",
        similarity_script="/workspaces/RevEng/support/binary_similarity.sh",
        library_name=project.name
        )

    iterations = comparison.discover_iterations()

    for file_number in sorted(iterations):
        paths = iterations[file_number]
        for log_path in sorted(paths):
            if not log_path.is_file():
                print(f"[!] Skipping non-file: {log_path}")
                continue
        log_text = log_path.read_text(
                            encoding="utf-8",
                            errors="replace",
                        )
        sections = comparison.split_iteration_sections(log_text)
        truth_extractor = gt_class()        
        if len(sections) < 2:
            print(
                f"[*] Skipping {log_path.name}: found only "
                f"{len(sections)} iteration section(s)"
            )
            continue
        first_iteration_number, first_iteration_text = sections[0]
        ground_truth_config = comparison.find_ground_truth_config(first_iteration_text)
        new_config = f"{ground_truth_config}_new"
        shutil.copy(ground_truth_config, new_config)
        ground_truth_config = new_config
        log_file = f"{project.name}_{run_id}.log"
        log_file = os.path.join(log_dir, log_file)
        with open(log_file, "w") as f, redirect_stdout(f):
            print(f"*** Run {run_id} for project: {project.name} ***")
            
            print("Ground_truth_config", ground_truth_config)
            flags = truth_extractor.extract(ground_truth_config, project.name, project.source_dir)
            truth_extractor.flags = flags
            print("FLAGS:", truth_extractor.flags)
            runner = ExperimentRunner(
                        build_manager=BuildrootOptOs(project.build_dir, project.source_dir),
                        locator=ConfigLocator(),
                        recovery=FlagRecoveryRunner(),
                        truth_extractor=truth_extractor,
                        comparator=ResultComparator(),
                    )
        
            print("Running experiment...")
            result = runner.run_project_iteratively(project,"filter")
            print("Result:", result)
            runner.build_manager.build_config(project, truth_extractor)
            if result.precision is not None:
                collected.append(result)
                print(f"[+] Accepted config #{accepted_id}")
        run_id = run_id +1
    return project.name






if __name__ == "__main__":
    projects = [
        Project(
            name='libcurl',
            source_dir=Path('/workspaces/RevEng/libcurl-7.29.0/lib/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/'),
            include_dir=Path('/workspaces/RevEng/libcurl-7.29.0/lib/'),
            metadata={
                'binary': Path('/workspaces/RevEng/libcurl-karonte'),
                'config_h': Path('/workspaces/RevEng/libcurl-7.29.0/lib/curl_config.h'),
                'cflags': '',
                'include': '/workspaces/RevEng/libcurl-7.29.0/include/',
            },
        ),
        Project(
            name='libcurl',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libcurl-7.71.1/lib/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libcurl-7.71.1/lib/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libcurl-7.71.1/lib/.libs/libcurl.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libcurl-7.71.1/lib/curl_config.h'),
                'cflags': '',
                'include': '/workspaces/RevEng/buildroot-2025.02.4/output/build/libcurl-7.71.1/include/',
            },
        ),
        Project(
            name='dbus',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/dbus-1.14.10/dbus'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/dbus-1.14.10/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/dbus-1.14.10/dbus/.libs/libdbus-1.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/dbus-1.14.10/config.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='dropbear',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/dropbear-2025.88/src'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/dropbear-2025.88/src'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/dropbear-2025.88/dropbearmulti'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/dropbear-2025.88/src/default_options.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='expat',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/expat-2.7.1/lib/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/expat-2.7.1/lib/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/expat-2.7.1/lib/.libs/libexpat.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/expat-2.7.1/expat_config.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='flac',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/flac-1.4.3/src/libFLAC/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/flac-1.4.3/src/libFLAC/include/private/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/flac-1.4.3/src/libFLAC/.libs/libFLAC.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/flac-1.4.3/config.h'),
                'cflags': '',
            },
        ),
        Project(
            name='libpcap',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libpcap-1.10.5/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libpcap-1.10.5/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libpcap-1.10.5/libpcap.so.1.10.5'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libpcap-1.10.5/config.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='nano',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/nano-8.2/src/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/nano-8.2/src/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/nano-8.2/src/nano'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/nano-8.2/config.h'),
                'cflags': '',
                'include': '/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/nano-8.2/lib/',
            },
        ),
        Project(
            name='ncurses',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/ncurses-6.4-20230603/ncurses/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/ncurses-6.4-20230603/ncurses/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/ncurses-6.4-20230603/lib/libncurses.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/ncurses-6.4-20230603/include/ncurses_cfg.h'),
                'cflags': '',
                'include': '/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/ncurses-6.4-20230603/include/',
            },
        ),
        Project(
            name='pcre2',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/pcre2-10.44/src/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/pcre2-10.44/src/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/pcre2-10.44/.libs/libpcre2-8.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/pcre2-10.44/src/config.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='rsync',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/rsync-3.4.1/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/rsync-3.4.1/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/rsync-3.4.1/rsync'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/rsync-3.4.1/config.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='tcpdump',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/tcpdump-4.99.5/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/tcpdump-4.99.5/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/tcpdump-4.99.5/tcpdump'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/tcpdump-4.99.5/config.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='xz',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/xz-5.6.4/src/liblzma/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/xz-5.6.4/src/liblzma/common/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/xz-5.6.4/src/liblzma/.libs/liblzma.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/xz-5.6.4/config.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='sqlite',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/sqlite-3.48.0/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/sqlite-3.48.0/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/sqlite-3.48.0/sqlite3'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/sqlite-3.48.0/README.txt'),
                'cflags': '-DSQLITE_ENABLE_FTS5 -DSQLITE_ENABLE_JSON1 -DSQLITE_ENABLE_FTS3 -DSQLITE_ENABLE_STAT4 -DSQLITE_ENABLE_RTREE -DSQLITE_ENABLE_JSON1 -DSQLITE_ENABLE_GEOPOLY -DSQLITE_ENABLE_MATH_FUNCTIONS',
                'include': '',
            },
        ),
        Project(
            name='libxml2',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libxml2-2.13.8/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libxml2-2.13.8/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libxml2-2.13.8/.libs/libxml2.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libxml2-2.13.8/include/libxml/xmlversion.h'),
                'cflags': '',
                'include': '/workspaces/RevEng/buildroot-2025.copy/output/build/libxml2-2.13.8/include/',
            },
        ),
        Project(
            name='libxslt',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libxslt-1.1.42/libxslt/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libxslt-1.1.42/libxslt/.libs/libxslt.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libxslt-1.1.42/config.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='libssh2',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/libssh2-1.11.0/src/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/libssh2-1.11.0/src/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/libssh2-1.11.0/src/.libs/libssh2.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy-optimization/output/build/libssh2-1.11.0/src/libssh2_config.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='libvpx',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libvpx-1.15.0/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libvpx-1.15.0'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libvpx-1.15.0/libvpx.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libvpx-1.15.0/vpx_config.h'),
                'cflags': '',
            },
        ),
        Project(
            name='libarchive',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libarchive-3.7.9/libarchive/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libarchive-3.7.9/libarchive/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libarchive-3.7.9/.libs/libarchive.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libarchive-3.7.9/config.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='libopenssl',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libopenssl-3.4.1/crypto/'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libopenssl-3.4.1/include/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libopenssl-3.4.1/libcrypto.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.02.4/output/build/libopenssl-3.4.1/include/openssl/configuration.h'),
                'cflags': '',
                'include': '',
            },
        ),
        Project(
            name='libopenssl',
            source_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libopenssl-3.4.1/ssl'),
            build_dir=Path('/workspaces/RevEng/buildroot-2025.copy/'),
            include_dir=Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libopenssl-3.4.1/include/'),
            metadata={
                'binary': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libopenssl-3.4.1/libssl.so'),
                'config_h': Path('/workspaces/RevEng/buildroot-2025.copy/output/build/libopenssl-3.4.1/include/openssl/configuration.h'),
                'cflags': '',
                'include': '',
            },
        ),
    ]


   
   
    with Pool(processes=1) as p:
        for res in p.imap_unordered(run_project_safe, projects):
            
            if res["status"] == "ok":
                print(f"✅ {res['project']} done")
            else:
                print(f"❌ {res['project']} failed: {res['error']}")