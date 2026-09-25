from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import re
import subprocess
import os
from dataclasses import dataclass
from z3.z3 import *

@dataclass
class Feature:
    name: str
    macros: list[str]


class FeatureExtractor:
    """
    Class to get a mapping of all the features from a configure script to the macros they enable. 
    This is then used to infer the correct macro combination of the built binary.
    """ 
    def __init__(self):
        self.feature_map: dict
        self.macros: list = []
        self.features: list[Feature]
        

    def extract(self, configure_ac_path: Path, m4_constraints_path: Path):
        """ 
        1. Append the extra m4 definitions to the configure file (configure.ac or configure.in)
        2. Run autom4te on the configure.ac or configure.in script with the modified extract.m4 Macros.
        3. Parse the resulting file to a list of dictionaries
        4. Connect enable and with features to the corresponding Macros
        """
        enable_json=Path(str(configure_ac_path.cwd()) + "/enable-options.json")    
            
        results = parse_macro_file(enable_json)

        self.feature_map = self.connect_features_and_macros(results)
        return results


    def connect_features_and_macros(self, options: list) -> dict:
        result = dict()
        for option in options:
            try:
                if option['definition'] != "":
                    macros = [m.strip() for m in option['definition'].split(';') if m.strip()]
                    self.macros.append(macros)
                    enable_match = re.search(r'--enable-[\w-]+', option["help"])
                    disable_match = re.search(r'--disable-[\w-]+', option["help"])

                    if enable_match:
                        result[enable_match.group()] = [m for m in macros if 'ENABLE' in m.upper()]

                    if disable_match:
                        result[disable_match.group()] = [m for m in macros if 'DISABLE' in m.upper()]
            except KeyError:
                print("Key does not exist")
        self.feature_map = result      
        return result
        

    def macros_as_z3(self) -> dict[str, dict[str, BoolRef]]:
        """
        Returns:
          {
            '--disable-http': {
                'CURL_DISABLE_HTTP': BoolRef,
                'CURL_DISABLE_RTSP': BoolRef
            },
            ...
          }
        """
        result: dict[str, dict[str, BoolRef]] = {}

        for flag, macros in self.feature_map.items():
            macro_bool = True

            for macro in macros:
                name = macro.split("=", 1)[0]
                boolo = Bool(name)
                macro_bool = And(macro_bool, boolo)
            result[flag] = macro_bool

        return result



def parse_macro_file(path) -> list:
    """
    Parses a file containing lines with 'name', 'help', 'definition' fields.
    Returns a list of dicts.
    """
    entries = []
    current = defaultdict(str)
    accumulating_help = False

    name_re = re.compile(r'name:\s*["\']?(.*?)(["\']|$)')
    help_re = re.compile(r'help:\s*["\']?(.*?)(["\']|$)')
    def_re  = re.compile(r'definition:\s*["\']?(.*?)(["\']|$)')

    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()
            if not line:
                accumulating_help = False
                continue

            m = name_re.search(line)
            if m:
                if current:
                    entries.append(dict(current))
                    current.clear()
                current['name'] = m.group(1).strip()
                accumulating_help = False
                continue

            m = help_re.search(line)
            if m:
                help_text = m.group(1).strip()
                if 'help' in current:
                    current['help'] += '\n' + help_text
                else:
                    current['help'] = help_text
                accumulating_help = True
                continue

            m = def_re.search(line)
            if m:
                current['definition'] = m.group(1).strip()
                accumulating_help = False
                continue

            if accumulating_help:
                current['help'] +=  line.strip()

    if current:
        entries.append(dict(current))

    return entries






def append_enable_json_block(configure_ac_path: str) -> None:
    block = """m4_define([_ENABLE_JSON],
[
[
]m4_esyscmd([
printf "%s" "m4_defn([_ENABLE_JSON_ENTRIES])" | sed '$ s/,$//'
])[
]]])

m4_syscmd([
cat > enable-options.json <<'EOF'
]_ENABLE_JSON[
EOF
])
"""

    with open(configure_ac_path, "a", encoding="utf-8") as f:
        f.write("\n" + block)



def run(cwd, command):
    """
    Run a shell command :command: in the specified directory :cwd:
    """
    print(command)
    try:
        result = subprocess.run(command, cwd=cwd, check=True, capture_output=True,text=True)
    except subprocess.CalledProcessError as c:
        pass
    