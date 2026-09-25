import random
import shutil
import subprocess
import re
from pathlib import Path


class GroundTruthExtractor:
    def __init__(self):
        self.flags = set()

    def mix_cflags(self, project):
        return ""


    def clean_conflicts(self):
        pass

    def load_flags_from_config(self, config_path):
  
        
        flag_names = {name for name, _ in self.flags}

        parsed_flags = {}

        with open(config_path, "r") as f:
            for line in f:
                line = line.strip()

                m_define = re.match(r"#define\s+(\w+)", line)
                if m_define:
                    flag = m_define.group(1)
                    if flag in flag_names:
                        parsed_flags[flag] = "True"
                    continue

                m_undef = re.match(r"/\*\s*#undef\s+(\w+)\s*\*/", line)
                if m_undef:
                    flag = m_undef.group(1)
                    if flag in flag_names:
                        parsed_flags[flag] = "False"

        updated_flags = set()
        for flag, _ in self.flags:
            if flag in parsed_flags:
                updated_flags.add((flag, parsed_flags[flag]))
        print("THOSE ARE THE UPDATED FLAGS:", updated_flags)
        self.flags = updated_flags
        




    def mix(self):
        
        flags = set_to_dict(self.flags)
        print("Flags before mixing", flags)
        for key in flags:
            flags[key] = random.choice([True, False])

        self.flags = dict_to_set(flags)
        print("Flags after mixing", self.flags)

    def extract(self, config_h: Path, name: str, src_dir: Path) -> set[(str,str)]:
            
        flags = self.modify_config_h(config_h, name)
        
        flags = self.remove_dead_macros(config_h, src_dir, flags)

        
        return flags




        
                    
                        

    def modify_config_h(self, config_h, name: str) -> set[(str,str)]:
        DEFINE_BOOL_RE = re.compile(r'^\s*#define\s+([A-Z0-9_]+)\s+(?:0|1)\s*$')
        UNDEF_RE = re.compile(r'^\s*/\*\s*#undef\s+([A-Z0-9_]+)\s*\*/\s*$')
        DEFINE_OTHER_RE = re.compile(r'^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\b(?!\s*\()')

        path = str(config_h)
        out_path = "/workspaces/RevEng/header/other_defines/other_defines" + name + ".h"
        flags = set()    
        with open(path, "r", encoding="utf-8", errors="ignore") as f, \
            open(out_path, "w", encoding="utf-8") as out:
            out.write("/* Auto-extracted non-boolean defines */\n\n")
            for line in f:
                print(line.rstrip())
                handled = False
                match = DEFINE_BOOL_RE.match(line)
                if match:
                    macro_name = match.group(1)
                    flags.add((macro_name,"True"))
                    handled = True
                m_undef = UNDEF_RE.match(line)
                if m_undef:
                    macro_name = m_undef.group(1)                    
                    handled = True
                    flags.add((macro_name,"False"))
                if not handled:
                    m_other = DEFINE_OTHER_RE.match(line)
                    if m_other:
                        out.write(line)
            
        destination = "/workspaces/RevEng/header/libraries/" + name + ".h"
        shutil.move(path, destination)   

        return flags



    def remove_dead_macros(self, src_dir: Path, macros) -> set[str]:
        
        unused = []

        for (macro, _) in macros:
            
            try:
                res = subprocess.check_output([
                    "grep", "-Rqw",
                    "--include=*.c",
                    "--include=*.h",
                    "--include=*.cpp",
                    "--include=*.hpp",
                    "--include=*.cc",
                    "--exclude=config.h",
                    macro,
                    src_dir
                ])
                
            except subprocess.CalledProcessError:
                unused.append(macro)
                print("Macro %s is unused." % macro)
        new_macros = set()
        for m in macros:
            if m[0] not in unused:
                new_macros.add(m)   

        return new_macros        


def dict_to_set(flags_dict):
    return {(k, str(v)) for k, v in flags_dict.items()}

def set_to_dict(flags_set):
    return {k: (v == "True") for k, v in flags_set}

 

        