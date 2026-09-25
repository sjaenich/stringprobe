from .config_truth import GroundTruthExtractor, dict_to_set, set_to_dict
import random 
import re
import shutil

class Libxml2GroundTruth(GroundTruthExtractor):

    def __init__(self):
        self.flags = set()
        self.flags.add(("LIBXML_C14N_ENABLED", "True"))
        self.flags.add(("LIBXML_CATALOG_ENABLED", "True"))
        self.flags.add(("LIBXML_DEBUG_ENABLED", "True")) 
    

        self.flags.add(("LIBXML_FTP_ENABLED", "False"))
        self.flags.add(("LIBXML_HISTORY_ENABLED", "False"))

        self.flags.add(("LIBXML_HTML_ENABLED", "True"))
        self.flags.add(("LIBXML_HTTP_ENABLED", "False"))

        self.flags.add(("LIBXML_ICONV_ENABLED", "True"))
        self.flags.add(("LIBXML_ICU_ENABLED", "False"))
        self.flags.add(("LIBXML_ISO8859X_ENABLED", "True"))

        self.flags.add(("LIBXML_LZMA_ENABLED", "False"))

        self.flags.add(("LIBXML_MODULES_ENABLED", "True"))

        self.flags.add(("LIBXML_OUTPUT_ENABLED", "True"))
        self.flags.add(("LIBXML_PATTERN_ENABLED", "True"))
        self.flags.add(("LIBXML_PUSH_ENABLED", "True"))

        self.flags.add(("LIBXML_PYTHON_ENABLED", "True"))

        self.flags.add(("LIBXML_READER_ENABLED", "True"))
        self.flags.add(("LIBXML_REGEXP_ENABLED", "True"))

        self.flags.add(("LIBXML_SAX1_ENABLED", "True"))

        self.flags.add(("LIBXML_SCHEMAS_ENABLED", "True"))

        self.flags.add(("LIBXML_SCHEMATRON_ENABLED", "True"))

        self.flags.add(("LIBXML_THREAD_ENABLED", "True"))
        self.flags.add(("LIBXML_THREAD_ALLOC_ENABLED", "False"))

        self.flags.add(("LIBXML_TREE_ENABLED", "True"))

        self.flags.add(("LIBXML_VALID_ENABLED", "True"))

        self.flags.add(("LIBXML_WRITER_ENABLED", "True"))

        self.flags.add(("LIBXML_XINCLUDE_ENABLED", "True"))
        self.flags.add(("LIBXML_XPATH_ENABLED", "True"))

        self.flags.add(("LIBXML_XPTR_ENABLED", "True"))
        self.flags.add(("LIBXML_XPTR_LOCS_ENABLED", "False"))

        self.flags.add(("LIBXML_ZLIB_ENABLED", "False"))

        self.flags.add(("LIBXML_MINIMUM_ENABLED", "False"))
        self.flags.add(("LIBXML_LEGACY_ENABLED", "False"))

        self.flags.add(("LIBXML_TLS_ENABLED", "False"))


    def mix(self):
        flags = {k: (v == "True") for k, v in self.flags}
        
        flags["LIBXML_TREE_ENABLED"] = True
        flags["LIBXML_OUTPUT_ENABLED"] = True

        flags["LIBXML_XPATH_ENABLED"] = random.choice([True, False])
        flags["LIBXML_PATTERN_ENABLED"] = random.choice([True, False])
        flags["LIBXML_REGEXP_ENABLED"] = random.choice([True, False])
        flags["LIBXML_PUSH_ENABLED"] = random.choice([True, False])

        flags["LIBXML_XPTR_ENABLED"] = (
            flags["LIBXML_XPATH_ENABLED"]
            and random.choice([True, False])
        )

        flags["LIBXML_XPTR_LOCS_ENABLED"] = (
            flags["LIBXML_XPTR_ENABLED"]
            and random.choice([True, False])
        )

        flags["LIBXML_XINCLUDE_ENABLED"] = (
            flags["LIBXML_XPATH_ENABLED"]
            and random.choice([True, False])
        )

        flags["LIBXML_C14N_ENABLED"] = (
            flags["LIBXML_XPATH_ENABLED"]
            and flags["LIBXML_OUTPUT_ENABLED"]
            and random.choice([True, False])
        )

        flags["LIBXML_SCHEMATRON_ENABLED"] = (
            flags["LIBXML_PATTERN_ENABLED"]
            and flags["LIBXML_TREE_ENABLED"]
            and flags["LIBXML_XPATH_ENABLED"]
            and random.choice([True, False])
        )

        schemas_enabled = (
            flags["LIBXML_PATTERN_ENABLED"]
            and flags["LIBXML_REGEXP_ENABLED"]
            and random.choice([True, False])
        )

        flags["LIBXML_SCHEMAS_ENABLED"] = schemas_enabled

        flags["LIBXML_READER_ENABLED"] = (
            flags["LIBXML_PUSH_ENABLED"]
            and flags["LIBXML_TREE_ENABLED"]
            and random.choice([True, False])
        )

        flags["LIBXML_WRITER_ENABLED"] = (
            flags["LIBXML_PUSH_ENABLED"]
            and flags["LIBXML_OUTPUT_ENABLED"]
            and random.choice([True, False])
        )


        flags["LIBXML_FTP_ENABLED"] = False
        flags["LIBXML_DEBUG_ENABLED"] = False

        independents = [
            "LIBXML_HTML_ENABLED",
            "LIBXML_SAX1_ENABLED",
            "LIBXML_CATALOG_ENABLED",
            "LIBXML_MODULES_ENABLED",
            "LIBXML_HTTP_ENABLED",
            "LIBXML_VALID_ENABLED",
        ]

        for key in independents:
            flags[key] = random.choice([True, False])

        self.flags = {(k, str(v)) for k, v in flags.items()}



    def clean_conflicts(self):
        flags = set_to_dict(self.flags)
        flags["LIBXML_FTP_ENABLED"] = False
        flags["LIBXML_DEBUG_ENABLED"] = False
        if any(
            flags[name]
            for name in (
                "LIBXML_XPTR_ENABLED",
                "LIBXML_SCHEMAS_ENABLED",
                "LIBXML_SCHEMATRON_ENABLED",
                "LIBXML_XINCLUDE_ENABLED",
                "LIBXML_C14N_ENABLED",
            )
        ):
            flags["LIBXML_XPATH_ENABLED"] = True
        
        if (
            flags["LIBXML_SCHEMAS_ENABLED"]
        ):
            flags["LIBXML_PATTERN_ENABLED"] = True
            flags["LIBXML_REGEXP_ENABLED"] = True
            flags["LIBXML_AUTOMATA_ENABLED"] = True


        if flags["LIBXML_WRITER_ENABLED"]:
            flags["LIBXML_OUTPUT_ENABLED"] = True
            flags["LIBXML_PUSH_ENABLED"] = True
            flags["LIBXML_TREE_ENABLED"] = True


        if (
            flags["LIBXML_CATALOG_ENABLED"] == True
            and flags["LIBXML_OUTPUT_ENABLED"] == True
        ):
            flags["LIBXML_TREE_ENABLED"] = True



        self.flags = dict_to_set(flags)



    def extract(self, config_h, name, src_dir):
        flags = set()
        flags.update(self.flags)

        flags = self.remove_dead_macros(src_dir, flags)
        print("Remaining macros after removing unused ones:", flags)
        only_flags = {flag for (flag, _) in flags}
        print("Only flag names:", only_flags)
        flags = self.modify_config_h(config_h, name, only_flags)
        print("Final set of macros after modifying config.h:", flags)
        return flags
        


    def modify_config_h(self, config_h, name: str, flags: set[str]):
        IF_RE = re.compile(r"^\s*#if\s+([01])\s*$")
        DEFINE_RE = re.compile(r"^\s*#define\s+([A-Za-z_][A-Za-z0-9_]*)\s*$")
        ENDIF_RE = re.compile(r"^\s*#endif\b")

        path = str(config_h)
        destination = f"/workspaces/RevEng/header/libraries/{name}.h"
        out_path = (
            f"/workspaces/RevEng/header/other_defines/"
            f"other_defines{name}.h"
        )

        updated_flags = set()

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        with open(destination, "w", encoding="utf-8") as dest, \
            open(out_path, "w", encoding="utf-8") as out:

            out.write("/* Auto-extracted non-boolean defines */\n\n")

            i = 0
            while i < len(lines):
                if (
                    i + 2 < len(lines)
                    and (if_match := IF_RE.match(lines[i]))
                    and (define_match := DEFINE_RE.match(lines[i + 1]))
                    and ENDIF_RE.match(lines[i + 2])
                ):
                    enabled = if_match.group(1) == "1"
                    macro_name = define_match.group(1)
                    block = lines[i:i + 3]

                    if macro_name in flags:
                        updated_flags.add((macro_name, str(enabled)))
                        dest.writelines(block)
                    else:
                        out.writelines(block)

                    i += 3
                    continue

                i += 1

        return updated_flags
