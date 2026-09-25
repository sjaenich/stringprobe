import random

from .config_truth import GroundTruthExtractor, dict_to_set, set_to_dict
import subprocess
import re
import shutil
from pathlib import Path

class LiblzmaFeatureTruth(GroundTruthExtractor):

    def __init__(self):
        self.flags = set()
        
        
        self.flags.add(("HAVE_CHECK_CRC32", "True"))
        self.flags.add(("HAVE_CHECK_CRC64", "True"))
        self.flags.add(("HAVE_CHECK_SHA256", "True"))
        
    
        
        self.flags.add(("HAVE_MF_HC3", "True"))
        self.flags.add(("HAVE_MF_HC4", "True"))
        self.flags.add(("HAVE_MF_BT2", "True"))
        self.flags.add(("HAVE_MF_BT3", "True"))
        self.flags.add(("HAVE_MF_BT4", "True"))
        
        self.flags.add(("HAVE_DECODERS", "True"))
        self.flags.add(("HAVE_ENCODERS","True"))
        self.flags.add(("HAVE_ENCODER_LZMA1", "True"))
        self.flags.add(("HAVE_ENCODER_LZMA2", "True"))
        self.flags.add(("HAVE_DECODER_LZMA1", "True"))
        self.flags.add(("HAVE_DECODER_LZMA2", "True"))
        archs = ["X86", "ARM", "ARM64", "ARMTHUMB", "POWERPC", "IA64", "SPARC", "RISCV"]
        for arch in archs:
            self.flags.add((f"HAVE_ENCODER_{arch}", "True"))
            self.flags.add((f"HAVE_DECODER_{arch}", "True"))

        for tech in ["LZMA1", "LZMA2", "DELTA"]:
            self.flags.add((f"HAVE_ENCODER_{tech}", "True"))
            self.flags.add((f"HAVE_DECODER_{tech}", "True"))
        
        self.flags.add(("HAVE_SMALL", "False"))


    def mix(self):
        flags = set_to_dict(self.flags)

        archs = [
            "X86",
            "ARM",
            "ARM64",
            "ARMTHUMB",
            "POWERPC",
            "IA64",
            "SPARC",
            "RISCV",
        ]

        filters = ["LZMA1", "LZMA2", "DELTA", *archs]

        encoder_flags = [f"HAVE_ENCODER_{name}" for name in filters]
        decoder_flags = [f"HAVE_DECODER_{name}" for name in filters]
        match_finder_flags = [
            "HAVE_MF_HC3",
            "HAVE_MF_HC4",
            "HAVE_MF_BT2",
            "HAVE_MF_BT3",
            "HAVE_MF_BT4",
        ]


        flags["HAVE_SMALL"] = random.choice([True, False])

        flags["HAVE_CHECK_CRC32"] = True
        flags["HAVE_CHECK_CRC64"] = random.choice([True, False])
        flags["HAVE_CHECK_SHA256"] = random.choice([True, False])


        enable_encoders = random.choice([True, False])
        enable_decoders = random.choice([True, False])

        for key in encoder_flags:
            flags[key] = (
                random.choice([True, False])
                if enable_encoders
                else False
            )

        for key in decoder_flags:
            flags[key] = (
                random.choice([True, False])
                if enable_decoders
                else False
            )

        if enable_encoders and not any(flags[key] for key in encoder_flags):
            flags[random.choice(encoder_flags)] = True

        if enable_decoders and not any(flags[key] for key in decoder_flags):
            flags[random.choice(decoder_flags)] = True


        if flags["HAVE_ENCODER_LZMA2"]:
            flags["HAVE_ENCODER_LZMA1"] = True

        if flags["HAVE_DECODER_LZMA2"]:
            flags["HAVE_DECODER_LZMA1"] = True

        flags["HAVE_ENCODERS"] = any(
            flags[key] for key in encoder_flags
        )
        flags["HAVE_DECODERS"] = any(
            flags[key] for key in decoder_flags
        )

        have_lz_encoder = (
            flags["HAVE_ENCODER_LZMA1"]
            or flags["HAVE_ENCODER_LZMA2"]
        )

        if have_lz_encoder:
            for key in match_finder_flags:
                flags[key] = random.choice([True, False])

            if not any(flags[key] for key in match_finder_flags):
                flags[random.choice(match_finder_flags)] = True
        else:
            for key in match_finder_flags:
                flags[key] = False


        self.flags = dict_to_set(flags)

    def clean_conflicts(self):
        print("Cleaning conflicts for liblzma...")
        flags = set_to_dict(self.flags)
        print("Flags before cleaning:", flags)
        flags['HAVE_DECODERS'] = False
        flags["HAVE_ENCODERS"] = False
        archs = ["X86", "ARM", "ARM64", "ARMTHUMB", "POWERPC", "IA64", "SPARC", "RISCV"]
        for arch in archs:
            if f"HAVE_ENCODER_{arch}" in flags:
                if flags[f"HAVE_ENCODER_{arch}"]:
                    flags["HAVE_ENCODERS"] = True
            if f"HAVE_DECODER_{arch}" in flags:        
                if flags[f"HAVE_DECODER_{arch}"]:
                    flags["HAVE_DECODERS"] = True
            
        for tech in ["LZMA1", "LZMA2", "DELTA"]:
            if f"HAVE_ENCODER_{tech}" in flags:
                if flags[f"HAVE_ENCODER_{tech}"]:
                    flags["HAVE_ENCODERS"] = True
            
            if f"HAVE_DECODER_{tech}" in flags:
                if flags[f"HAVE_DECODER_{tech}"]:
                    flags["HAVE_DECODERS"] = True
        
                    
        self.flags = dict_to_set(flags)



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
        DEFINE_OTHER_RE = re.compile(r'^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\b(?!\s*\()')

        path = str(config_h)
        out_path = f"/workspaces/RevEng/header/other_defines/other_defines_{name}.h"
        destination = f"/workspaces/RevEng/header/libraries/{name}.h"
        
        updated_flags = set()

        with open(path, "r", encoding="utf-8", errors="ignore") as f, \
             open(destination, "w", encoding="utf-8") as dest, \
             open(out_path, "w", encoding="utf-8") as out:
            
            out.write(f"/* liblzma - User-Controllable Feature Flags */\n\n")
            
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