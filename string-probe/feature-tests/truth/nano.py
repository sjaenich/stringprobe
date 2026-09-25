from .config_truth import GroundTruthExtractor, set_to_dict, dict_to_set
import subprocess
import re
import shutil
from pathlib import Path

class NanoGroundTruth(GroundTruthExtractor):

    def __init__(self):
        self.flags = set()
        
        self.flags.add(("NANO_TINY", "True"))
        
        self.flags.add(("ENABLE_NANORC", "False"))
        self.flags.add(("ENABLE_COLOR", "False"))
        self.flags.add(("ENABLE_SPELLER", "False"))
        self.flags.add(("ENABLE_HELP", "False"))
        self.flags.add(("ENABLE_JUSTIFY", "False"))
        self.flags.add(("ENABLE_HISTORIES", "False"))
        self.flags.add(("ENABLE_TABCOMP", "False"))
        self.flags.add(("ENABLE_WRAPPING", "False"))
        self.flags.add(("ENABLE_BROWSER", "False"))
        self.flags.add(("ENABLE_NLS","False"))
        self.flags.add(("ENABLE_WORDCOMPLETION","False"))
        self.flags.add(("ENABLE_UTF8", "False"))
        self.flags.add(("ENABLE_MULTIBUFFER", "False"))
        self.flags.add(("ENABLE_LINENUMBERS", "False"))
        self.flags.add(("ENABLE_MOUSE", "False"))
        
        self.flags.add(("HAVE_LIBMAGIC", "False"))
        
        self.flags.add(("ENABLE_OPERATINGDIR", "False"))


    def clean_conflicts(self):
        flags = set_to_dict(self.flags)

        if flags["NANO_TINY"]:
            flags["ENABLE_WORDCOMPLETION"] = False

        if flags["ENABLE_HELP"] or not flags["NANO_TINY"]:
            flags["ENABLE_MULTIBUFFER"] = True


        if flags["ENABLE_COLOR"]:
            flags["ENABLE_NANORC"] = True

        self.flags = dict_to_set(flags)


    def extract(self, config_h, name, src_dir):
        flags = self.flags
 

        flags = self.remove_dead_macros(src_dir, flags)
        
        only_flags = set()
        for (flag, _) in flags:
            only_flags.add(flag)
            
        updated_flags = self.modify_config_h(config_h, name, only_flags)
        return updated_flags

    def modify_config_h(self, config_h, name: str, flags: set[str]) -> set:
        DEFINE_BOOL_RE = re.compile(r'^\s*#define\s+([A-Z0-9_]+)\s+(?:0|1)\s*$')
        UNDEF_RE = re.compile(r'^\s*/\*\s*#undef\s+([A-Z0-9_]+)\s*\*/\s*$')
        DEFINE_OTHER_RE = re.compile(r'^\s*#define\s+(ENABLE_[A-Z_]+|[A-Z_][A-Z0-9_]*)\b(?!\s*\()')

        path = str(config_h)
        out_path = f"/workspaces/RevEng/header/other_defines/other_defines_{name}.h"
        destination = f"/workspaces/RevEng/header/libraries/{name}.h"
        
        updated_flags = set()

        with open(path, "r", encoding="utf-8", errors="ignore") as f, \
             open(destination, "w", encoding="utf-8") as dest, \
             open(out_path, "w", encoding="utf-8") as out:
            
            out.write(f"/* GNU nano - User-Controllable Feature Flags */\n\n")
            
            for line in f:
                handled = False
                
                match = DEFINE_BOOL_RE.match(line)
                if match:
                    macro_name = match.group(1)
                    if macro_name in flags:
                        updated_flags.add((macro_name, "True"))
                        dest.write(line)
                        handled = True

                m_undef = UNDEF_RE.match(line)
                if m_undef:
                    macro_name = m_undef.group(1)
                    if macro_name in flags:
                        updated_flags.add((macro_name, "False"))
                        dest.write(line)
                        handled = True

                if not handled:
                    m_other = DEFINE_OTHER_RE.match(line)
                    if m_other:
                        out.write(line)

        return updated_flags

    def remove_dead_macros(self, src_dir: Path, macros) -> set:
        unused = []
        for (macro, _) in macros:
            try:
                subprocess.check_output([
                    "grep", "-Rqw", "--include=*.c", "--include=*.h", 
                    macro, str(src_dir)
                ])
            except subprocess.CalledProcessError:
                unused.append(macro)

        return {m for m in macros if m[0] not in unused}