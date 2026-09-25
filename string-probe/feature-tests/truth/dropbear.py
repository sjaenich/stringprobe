from .config_truth import GroundTruthExtractor
import subprocess
import re
import shutil
from pathlib import Path

class DropbearGroundTruth(GroundTruthExtractor):

    def __init__(self): 
        self.flags = set()
        print("Initializing DropbearGroundTruth with default flags")
        self.flags.add(("DROPBEAR_X11FWD", "False"))
        self.flags.add(("DROPBEAR_SFTPSERVER", "True"))
        
        
        
        self.flags.add(("DROPBEAR_AES128", "True"))
        self.flags.add(("DROPBEAR_AES256", "True"))
        self.flags.add(("DROPBEAR_CHACHA20POLY1305", "True"))
        self.flags.add(("DROPBEAR_3DES", "False"))
        
        self.flags.add(("DROPBEAR_ENABLE_GCM_MODE", "False"))
        
        self.flags.add(("DROPBEAR_CURVE25519", "True"))
        self.flags.add(("DROPBEAR_ECDH", "True"))
        self.flags.add(("DROPBEAR_DH_GROUP14_SHA1", "False"))
        
        self.flags.add(("DO_HOST_LOOKUP", "False"))

    def extract(self, config_h, name, src_dir):
        flags = self.flags

        flags = self.remove_dead_macros(src_dir, flags)
        
        only_flags = set()
        for (flag, _) in flags:
            only_flags.add(flag)
            
        flags = self.modify_config_h(config_h, name, only_flags)
        return flags

    def modify_config_h(self, config_h, name: str, flags: set[str]) -> set:
        DEFINE_BOOL_RE = re.compile(r'^\s*#define\s+([A-Z0-9_]+)\s+(?:0|1)\s*$')
        UNDEF_RE = re.compile(r'^\s*/\*\s*#undef\s+([A-Z0-9_]+)\s*\*/\s*$')
        DEFINE_OTHER_RE = re.compile(r'^\s*#define\s+(DROPBEAR_[A-Z_]+|[A-Z_][A-Z0-9_]*)\b(?!\s*\()')

        path = str(config_h)
        out_path = f"/workspaces/RevEng/header/other_defines/other_defines_{name}.h"
        destination = f"/workspaces/RevEng/header/libraries/{name}.h"
        
        updated_flags = set()

        with open(path, "r", encoding="utf-8", errors="ignore") as f, \
             open(destination, "w", encoding="utf-8") as dest, \
             open(out_path, "w", encoding="utf-8") as out:
            
            out.write(f"/* Dropbear SSH - Feature Toggles */\n\n")
            
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