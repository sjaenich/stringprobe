from sys import flags
import random
from .config_truth import GroundTruthExtractor, dict_to_set, set_to_dict
import subprocess
import re
import shutil
from pathlib import Path

import os
import re
import shutil

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path



LIBCRYPTO_FEATURE_MACROS = (

    "OPENSSL_NO_ARIA",
    "OPENSSL_NO_ASYNC",
    "OPENSSL_NO_ATEXIT",
    "OPENSSL_NO_AUTOERRINIT",
    "OPENSSL_NO_AUTOLOAD_CONFIG",
    "OPENSSL_NO_BF",
    "OPENSSL_NO_BLAKE2",
    "OPENSSL_NO_CACHED_FETCH",
    "OPENSSL_NO_CAMELLIA",
    "OPENSSL_NO_CAST",
    "OPENSSL_NO_CHACHA",
    "OPENSSL_NO_CMAC",
    "OPENSSL_NO_CMP",
    "OPENSSL_NO_CMS",
    "OPENSSL_NO_COMP",
    "OPENSSL_NO_CRYPTO_MDEBUG",
    "OPENSSL_NO_CT",
    "OPENSSL_NO_DEFAULT_THREAD_POOL",
    "OPENSSL_NO_DES",
    "OPENSSL_NO_DGRAM",
    "OPENSSL_NO_DH",
    "OPENSSL_NO_DSA",
    "OPENSSL_NO_EC",
    "OPENSSL_NO_EC2M",
    "OPENSSL_NO_ECX",
    "OPENSSL_NO_ENGINE",
    "OPENSSL_NO_ERR",
    "OPENSSL_NO_HTTP",
    "OPENSSL_NO_IDEA",
    "OPENSSL_NO_MD2",
    "OPENSSL_NO_MD4",
    "OPENSSL_NO_MDC2",
    "OPENSSL_NO_OCB",
    "OPENSSL_NO_OCSP",
    "OPENSSL_NO_PINSHARED",
    "OPENSSL_NO_POLY1305",
    "OPENSSL_NO_POSIX_IO",
    "OPENSSL_NO_RC2",
    "OPENSSL_NO_RC4",
    "OPENSSL_NO_RFC3779",
    "OPENSSL_NO_RMD160",
    "OPENSSL_NO_SCRYPT",
    "OPENSSL_NO_SEED",
    "OPENSSL_NO_SM2",
    "OPENSSL_NO_SM4",
    "OPENSSL_NO_SOCK",
    "OPENSSL_NO_SRP",
    "OPENSSL_NO_STDIO",
    "OPENSSL_NO_TS",
    "OPENSSL_NO_UI_CONSOLE",

)


DISABLE_CASCADES = {
    "OPENSSL_NO_BLAKE2": {
        "OPENSSL_NO_ARGON2",
    },
 
    "OPENSSL_NO_DES": {
        "OPENSSL_NO_MDC2",
    },
    "OPENSSL_NO_EC": {
        "OPENSSL_NO_EC2M",
        "OPENSSL_NO_ECX",
        "OPENSSL_NO_SM2",
    },
    "OPENSSL_NO_CMAC": {
        "OPENSSL_NO_SIV",
    },
    "OPENSSL_NO_SM3": {
        "OPENSSL_NO_SM2",
    },
    "OPENSSL_NO_ENGINE": {
        "OPENSSL_NO_LOADERENG",
        
    },
    "OPENSSL_NO_HTTP": {
        "OPENSSL_NO_OCSP",
    },
    "OPENSSL_NO_SOCK": {
        "OPENSSL_NO_DGRAM",
    },

    "OPENSSL_NO_THREAD_POOL": {
        "OPENSSL_NO_DEFAULT_THREAD_POOL",
    },
}

class OpensslGroundTruth(GroundTruthExtractor):
    def __init__(self):
        self.flags = {
            (macro_name, "False")
            for macro_name in LIBCRYPTO_FEATURE_MACROS
        }
        

    def mix(self):
        
        f = set_to_dict(self.flags)

        for macro_name in LIBCRYPTO_FEATURE_MACROS:
            if macro_name in f:
                f[macro_name] = random.choice([True, False])

        changed = True

        while changed:
            changed = False

            for parent_macro, dependent_macros in DISABLE_CASCADES.items():
                if not f.get(parent_macro, False):
                    continue

                for dependent_macro in dependent_macros:
                    if (
                        dependent_macro in f
                        and not f[dependent_macro]
                    ):
                        f[dependent_macro] = True
                        changed = True


        self.flags = dict_to_set(f)
        

    def extract(self, config_h, name, src_dir):
        
        flags = set()
        flags.update(self.flags)

        flags = self.remove_dead_macros(src_dir, flags)
        
        only_flags = {flag for (flag, _) in flags}
        flags = self.modify_config_h(config_h, name, only_flags)
        return flags


    def remove_dead_macros(self, src_dir: Path, macros) -> set:
        """
        Keep only macros referenced from libcrypto-relevant source.
        Search crypto/ plus public headers, not the whole OpenSSL tree.
        """
        search_roots = [
            src_dir
        ]

        unused = []
        print("Source directory:", src_dir)
        for (macro, _) in macros:
            found = False
            for root in search_roots:
                if not root.exists():
                    continue
                try:
                    subprocess.check_output([
                        "grep", "-Rqw",
                        "--include=*.c", "--include=*.h",
                        macro, str(root)
                    ])
                    found = True
                    break
                except subprocess.CalledProcessError:
                    pass

            if not found:
                unused.append(macro)
        print("Unused macros:", unused)
        return {m for m in macros if m[0] not in unused}

    def modify_config_h(self, config_h, name: str, flags: set[str]):
        block_re = re.compile(
            r"""
            ^[^\S\r\n]*\#[^\S\r\n]*ifndef[^\S\r\n]+
            (?P<guard>[A-Za-z_][A-Za-z0-9_]*)[^\S\r\n]*\r?\n

            ^[^\S\r\n]*\#[^\S\r\n]*define[^\S\r\n]+
            (?P<define>[A-Za-z_][A-Za-z0-9_]*)[^\S\r\n]*\r?\n

            ^[^\S\r\n]*\#[^\S\r\n]*endif\b[^\r\n]*(?:\r?\n|$)
            """,
            re.MULTILINE | re.VERBOSE,
        )

        destination = Path(f"/workspaces/RevEng/header/libraries/{name}.h")
        out_path = Path(
            f"/workspaces/RevEng/header/other_defines/other_defines_{name}.h"
        )


        updated_flags: set[tuple[str, str]] = set()
        defined_flags: set[str] = set()

        with open(config_h, "r", encoding="utf-8") as source:
            content = source.read()

        with (
            destination.open("w", encoding="utf-8") as dest,
            out_path.open("w", encoding="utf-8") as out,
        ):
            out.write("/* Auto-extracted blocks outside the requested flags */\n\n")

            for match in block_re.finditer(content):
                guard_name = match.group("guard")
                macro_name = match.group("define")

                if guard_name != macro_name:
                    continue

                if macro_name in flags:
                    if macro_name not in defined_flags:
                        defined_flags.add(macro_name)
                        updated_flags.add((macro_name, "True"))
                        dest.write(f"#define {macro_name}\n")
                else:
                    out.write(match.group(0))

            for macro_name in sorted(flags - defined_flags):
                updated_flags.add((macro_name, "False"))
                dest.write(f"#undef {macro_name}\n")

        return updated_flags