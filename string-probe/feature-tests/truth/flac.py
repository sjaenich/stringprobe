from .config_truth import GroundTruthExtractor
import subprocess
import re
import shutil
from pathlib import Path


class FlacGroundTruth(GroundTruthExtractor):
    def extract(self, config_h, name, src_dir):
        
        flags = set()
        flags.add(("FLAC__HAS_OGG", "False"))
        flags.add(("FLAC__USE_AVX", "True"))
        flags.add(("NDEBUG", "True"))
        flags.add(("FLAC__HAS_X86INTRIN", "True"))
        flags.add(("FLAC__HAS_NEONINTRIN", "False"))
        flags.add(("FLAC__USE_AVX2", "True"))
        flags.add(("FLAC__NO_ASM", "False"))
        flags.add(("FLAC__HAS_PANDOC", "False"))
        flags.add(("FLAC__ALIGN_MALLOC_DATA", "False"))
        flags.add(("ENABLE_64_BIT_WORDS", "True"))
        
    
        flags = self.remove_dead_macros(src_dir, flags)

        only_flags = {flag for (flag, _) in flags}

        flags = self.modify_config_h(config_h, name, only_flags)
        
        return flags


    def modify_config_h(self, config_h, name: str, flags: set[str]):
        DEFINE_BOOL_RE = re.compile(r'^\s*#define\s+([A-Z0-9_]+)\s+(?:0|1)\s*$')
        UNDEF_RE = re.compile(r'^\s*/\*\s*#undef\s+([A-Z0-9_]+)\s*\*/\s*$')
        DEFINE_OTHER_RE = re.compile(r'^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\b(?!\s*\()')

        path = str(config_h)
        out_path = f"/workspaces/RevEng/header/other_defines/other_defines{name}.h"
        destination = f"/workspaces/RevEng/header/libraries/{name}.h"
        
        with open(path, "r", encoding="utf-8", errors="ignore") as f, \
             open(destination, "w", encoding="utf-8") as dest, \
             open(out_path, "w", encoding="utf-8") as out:

            out.write("/* Auto-extracted non-boolean defines */\n\n")

            for line in f:
                handled = False

                match = DEFINE_BOOL_RE.match(line)
                if match:
                    macro_name = match.group(1)
                    if macro_name in flags:
                        flags.add((macro_name, "True"))
                        dest.write(line)
                        handled = True

                m_undef = UNDEF_RE.match(line)
                if m_undef:
                    macro_name = m_undef.group(1)
                    if macro_name in flags:
                        flags.add((macro_name, "False"))
                        dest.write(line)
                        handled = True

                if not handled:
                    m_other = DEFINE_OTHER_RE.match(line)
                    if m_other:
                        out.write(line)

        shutil.move(path, f"/workspaces/RevEng/header/libraries/{name}.old.h")

        return flags


    def remove_dead_macros(self, src_dir: Path, macros):
        unused = []

        for (macro, _) in macros:
            try:
                subprocess.check_output([
                    "grep", "-Rqw",
                    "--include=*.c",
                    "--include=*.h",
                    "--include=*.cpp",
                    "--include=*.hpp",
                    "--include=*.cc",
                    "--exclude=config.h",
                    macro,
                    str(src_dir)
                ])
            except subprocess.CalledProcessError:
                unused.append(macro)
                print(f"Macro {macro} is unused.")

        return {m for m in macros if m[0] not in unused}



