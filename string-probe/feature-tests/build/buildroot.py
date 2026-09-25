import cmd
import subprocess
import tempfile
import time
import os
import re
from pathlib import Path
from typing import List
from truth.config_truth import GroundTruthExtractor
import shutil
from core.project import Project, BuildResult
from build.builderror import BuildErrorPresenceExtractor
from z3.z3 import *

class BuildrootBuildManager:
    """
    Build a single Buildroot package and extract produced binaries.
    """

    def __init__(
        self,
        buildroot_dir: Path,
        output_base: Path,
        timeout: int = 300,
    ):
        self.buildroot_dir = buildroot_dir
        self.output_base = output_base
        self.timeout = timeout
        self.stdout = None
        self.stderr = None
        self.bundle = None
        
    def _run(self, cmd, cwd, log_file: Path, env=None):

        if env is None:
            env = os.environ.copy()


        with log_file.open("a") as f:
            return subprocess.run(
                cmd,
                cwd=cwd,
                stdout=f,
                stderr=subprocess.STDOUT,
                timeout=self.timeout,
                check=False,
                env=env,
            )

    def _ensure_clean_build(self, pkg: str, log_file: Path):
        self._run(
            ["make", pkg + "-dirclean"],
            self.buildroot_dir,
            log_file,
        )


    def _strip_library(self, project, log_file: Path):
        """
        Strip a compiled library using Buildroot's toolchain.
        """

        lib_path = project.metadata["binary"]

        
        
        
            

        strip = f"/workspaces/RevEng/buildroot-2025.02.4/output/host/bin/arm-buildroot-linux-gnueabihf-strip"

        if not lib_path.exists():
            raise FileNotFoundError(f"Library not found: {lib_path}")

        cmd = [str(strip), "--strip-unneeded", str(lib_path)]



        self._run(cmd, self.buildroot_dir, log_file)

        cmd = f"strings {str(lib_path)} >> /workspaces/RevEng/{project.name}_stripped_strings.txt"
        subprocess.run(cmd, shell=True)
        



    def _ensure_defconfig(self, out_dir: Path, log_file: Path):
        if not (out_dir / ".config").exists():
            self._run(
                ["make",  "defconfig"],
                self.buildroot_dir,
                log_file,
            )

    def _discover_binaries(self, target_dir: Path, pkg: str) -> List[Path]:
        
        if not target_dir.exists():
            return []

        pkg_lower = pkg.lower()

        bins = []
        for p in target_dir.rglob("*"):
            try:
                if (
                    p.is_file()
                    and (p.stat().st_mode & 0o111)
                    and pkg_lower in p.name.lower() and ".so" in p.name.lower()
                ):
                    bins.append(p)
            except OSError:
                pass

        return bins

    def _move_stripped_binary_and_config(self, project, log_file: Path, time):
        config_h = project.metadata.get("config_h", None)
        binary = project.metadata.get("binary", None)
        if not config_h or not binary:
            raise ValueError("Missing config_h or binary in project metadata")

        config_h = Path(config_h)
        binary = Path(binary)
        time = str(time)
        output_dir = log_file.parent / f"{project.name}_{time}_bundle"
        output_dir.mkdir(parents=True, exist_ok=True)

        dst_config = output_dir / config_h.name
        dst_binary = output_dir / binary.name

        shutil.copy2(config_h, dst_config)
        shutil.copy2(binary, dst_binary)
        return output_dir



    def _toggle_post_configure_hooks(self,file_path: Path, uncomment: bool = True):
        """
        Comment or uncomment all lines matching *_POST_CONFIGURE_HOOKS += ...

        :param file_path: Path to the .mk file
        :param uncomment: True -> uncomment, False -> comment
        """
        pattern = re.compile(r'^\s*#?\s*([A-Z0-9_]+_POST_CONFIGURE_HOOKS\s*\+=.*)$')

        lines = file_path.read_text().splitlines()
        new_lines = []

        for line in lines:
            match = pattern.match(line)

            if match:
                content = match.group(1).strip()
                indent = len(line) - len(line.lstrip())

                if uncomment:
                    line = " " * indent + content
                else:
                    line = " " * indent + "# " + content

            new_lines.append(line)

        file_path.write_text("\n".join(new_lines) + "\n")


    def rebuild_with_macros(self, project, gt: GroundTruthExtractor, frr: FlagRecovery, build_res: BuildResult):
        
                
        print("Cannot be compiled we need to install the corresponding libraries")
        return False
    

    def build_config(self, project: Project, gt: GroundTruthExtractor, iteration=None) -> Bool:
        pkg = project.name
        print(f"Building package {pkg} with ground truth flags: {gt.flags}")
        out_dir = self.buildroot_dir / "output/build/"
        log_file = out_dir / Path("buildroot_" + pkg + ".log")

        self._ensure_clean_build(pkg, log_file)

        cmd = [
            "make",
            f"{pkg}",
        ]

        env = os.environ.copy()

        env["MY_REAL_COMPILER"]=f"{"/workspaces/RevEng/buildroot-2025.02.4/output/host/bin/gcc-13.real"}"
        env["MY_EXTRA_FLAGS"]= gt.mix_cflags(project)
            

        


        res = self._run(cmd, self.buildroot_dir, log_file, env)

        success = res.returncode == 0

        return success


    def build(self, project: Project, gt: GroundTruthExtractor, iteration=None) -> BuildResult:
        
        pkg = project.name
        
        out_dir = self.buildroot_dir / "output/build/"

        log_file = out_dir / Path("buildroot_" + pkg + ".log")
        
        start = time.time()

        self._ensure_clean_build(pkg, log_file)

        print("Ground truth flags for project", project.name, ":", gt.flags)

        if project.name == "libopenssl":
            self.write_buildroot_hook_script_libopenssl(gt.flags, "/workspaces/RevEng/support/apply_" + project.name + "_truth.sh", project)
        elif project.name == "libxml2":
            self.write_buildroot_hook_script_libxml2(gt.flags, "/workspaces/RevEng/support/apply_" + project.name + "_truth.sh", project)
        else:
            self.write_buildroot_hook_script(gt.flags, "/workspaces/RevEng/support/apply_" + project.name + "_truth.sh", project)

        self._toggle_post_configure_hooks(self.buildroot_dir / "package" / pkg / (pkg + ".mk"), uncomment=True)
        cmd = [
            "make",
            f"{pkg}",
        ]

        env = os.environ.copy()

        env["MY_REAL_COMPILER"]=f"{"/workspaces/RevEng/buildroot-2025.02.4/output/host/bin/gcc-13.real"}"
        env["MY_EXTRA_FLAGS"]= gt.mix_cflags(project)
        env["SOURCE_DATE_EPOCH"] = "1704067200"

                            
            

        

        res = self._run(cmd, self.buildroot_dir, log_file, env)
        success = res.returncode == 0
        if not success:
            res = self._run(cmd, self.buildroot_dir, log_file, env)
            success = res.returncode == 0

        matches = list(out_dir.glob(f"{pkg}-*"))
        if not matches:
            raise FileNotFoundError(f"No build dir for {pkg}")
        target_dir = matches[0]
        output_dir = None
        dst_binary = None
        binaries = self._discover_binaries(target_dir, pkg) if success else []
        if success:
            self._strip_library(project, log_file)
            if iteration == 1:
                output_dir = self._move_stripped_binary_and_config(project, log_file, time.time())
                self.bundle = output_dir
            dst_binary = self.bundle / "final_binary"
            shutil.copy2(project.metadata["binary"], dst_binary)

        self._toggle_post_configure_hooks(self.buildroot_dir / "package" / pkg / (pkg + ".mk"), uncomment=False)

      

        os.remove(project.metadata.get("config_h", None))
        binaries = [project.metadata["binary"], dst_binary]
        duration = time.time() - start
        with log_file.open("a") as f:
            f.write(f"\n=== BUILD TIME: {duration:.2f}s ===\n")
        
        print(f"Build completed in {duration:.2f} seconds. Success: {success}. Binaries: {binaries}")
        return BuildResult(success=success,
            log_file=log_file,
            binary_paths=binaries,
            error="Rebuild Macros" if not success and iteration > 1 else None
        )


    def write_buildroot_hook_script(self, ground_truth_flags, script_path, project):
        """
        Writes a shell script that uses sed to toggle specific macros 
        in the _config.h file.
        """
        with open(script_path, 'w') as f:
            f.write("#!/bin/sh\n")
            f.write("CONFIG_H=\""+ str(project.metadata.get("config_h", "")) +"\"\n")
            f.write("echo \"Updating macros in $CONFIG_H\"\n")

            for macro, value in ground_truth_flags:
                if value == "True":
                    f.write(
                        f"sed -i 's@^#define[[:space:]]\\+{macro}[[:space:]].*@#define {macro} 1@' \"$CONFIG_H\"\n"
                    )
                    f.write(
                        f"sed -i 's@^/\\* #undef[[:space:]]\\+{macro}[[:space:]]\\*/@#define {macro} 1@' \"$CONFIG_H\"\n"
                    )
                else:
                    f.write(
                        f"sed -i 's@^#define[[:space:]]\\+{macro}[[:space:]].*@/* #undef {macro} */@' \"$CONFIG_H\"\n"
                    )


        os.chmod(script_path, 0o755)


    def write_buildroot_hook_script_libopenssl(
            self,
            ground_truth_flags,
            script_path,
            project,
    ):
        """
        Directly modify Buildroot's package/libopenssl/libopenssl.mk.

        Each invocation:

        1. Restores the original libopenssl.mk baseline.
        2. Converts OPENSSL_NO_* macros into Configure options.
        3. Appends those options to the existing ./Configure command.

        OPENSSL_NO_FEATURE=True  -> no-feature
        OPENSSL_NO_FEATURE=False -> enable-feature

        script_path is retained for compatibility with existing callers.
        """
        del script_path

        buildroot_dir = Path(project.build_dir)

        libopenssl_mk = (
            buildroot_dir
            / "package"
            / "libopenssl"
            / "libopenssl.mk"
        )

        if not libopenssl_mk.is_file():
            raise FileNotFoundError(
                f"Buildroot libopenssl.mk not found: {libopenssl_mk}"
            )

        backup_path = libopenssl_mk.with_name(
            "libopenssl.mk.reveng-original"
        )

        if not backup_path.exists():
            shutil.copy2(libopenssl_mk, backup_path)
            print(f"Created baseline backup: {backup_path}")

        shutil.copy2(backup_path, libopenssl_mk)

        option_name_overrides = {
            "OPENSSL_NO_AFALGENG": "afalgeng",
            "OPENSSL_NO_AUTOALGINIT": "autoalginit",
            "OPENSSL_NO_CAPIENG": "capieng",
            "OPENSSL_NO_DEVCRYPTOENG": "devcryptoeng",
            "OPENSSL_NO_EC_NISTP_64_GCC_128": "ec_nistp_64_gcc_128",
            "OPENSSL_NO_FIPS_SECURITYCHECKS": "fips-securitychecks",
            "OPENSSL_NO_LOADERENG": "loadereng",
            "OPENSSL_NO_PADLOCKENG": "padlockeng",
        }

        configure_options = []
        seen_macros = set()

        for macro, raw_value in sorted(
            ground_truth_flags,
            key=lambda item: item[0],
        ):
            if (
                not isinstance(macro, str)
                or not re.fullmatch(
                    r"[A-Za-z_][A-Za-z0-9_]*",
                    macro,
                )
            ):
                raise ValueError(f"Invalid macro name: {macro!r}")

            if macro in seen_macros:
                raise ValueError(f"Duplicate macro: {macro}")

            seen_macros.add(macro)

            if isinstance(raw_value, bool):
                macro_defined = raw_value
            elif raw_value == "True":
                macro_defined = True
            elif raw_value == "False":
                macro_defined = False
            else:
                raise ValueError(
                    f"Invalid value for {macro}: {raw_value!r}; "
                    "expected True, False, 'True', or 'False'"
                )

            if macro == "OPENSSL_NO_DEPRECATED_3_0":
                option = (
                    "no-deprecated"
                    if macro_defined
                    else "enable-deprecated"
                )
                configure_options.append(option)
                continue

            if not macro.startswith("OPENSSL_NO_"):
                raise ValueError(
                    "Cannot map macro to an OpenSSL Configure option: "
                    f"{macro}"
                )

            option_name = option_name_overrides.get(macro)

            if option_name is None:
                option_name = (
                    macro.removeprefix("OPENSSL_NO_")
                    .lower()
                    .replace("_", "-")
                )

            prefix = "no-" if macro_defined else "enable-"
            configure_options.append(prefix + option_name)

        if not configure_options:
            raise ValueError(
                "No OpenSSL Configure options were generated"
            )

        original_text = libopenssl_mk.read_text(encoding="utf-8")

        configure_start = original_text.find(
            "define LIBOPENSSL_CONFIGURE_CMDS"
        )

        if configure_start == -1:
            raise RuntimeError(
                "Could not find LIBOPENSSL_CONFIGURE_CMDS in "
                f"{libopenssl_mk}"
            )

        configure_end = original_text.find(
            "\nendef",
            configure_start,
        )

        if configure_end == -1:
            raise RuntimeError(
                "Could not find the end of "
                "LIBOPENSSL_CONFIGURE_CMDS"
            )

        configure_block = original_text[
            configure_start:configure_end
        ]

        configure_lines = configure_block.splitlines(
            keepends=True
        )

        configure_line_index = None

        for index, line in enumerate(configure_lines):
            if re.match(
                r"^[ \t]*\./Configure(?:[ \t]+\\)?[ \t]*$",
                line.rstrip("\r\n"),
            ):
                configure_line_index = index
                break

        if configure_line_index is None:
            raise RuntimeError(
                "Could not find ./Configure inside "
                "LIBOPENSSL_CONFIGURE_CMDS"
            )

        def line_continues(line):
            return line.rstrip("\r\n").rstrip().endswith("\\")

        command_end_index = configure_line_index

        while line_continues(
            configure_lines[command_end_index]
        ):
            command_end_index += 1

            if command_end_index >= len(configure_lines):
                raise RuntimeError(
                    "Could not find the final line of "
                    "the OpenSSL Configure command"
                )

        final_line = configure_lines[command_end_index]

        if not final_line.strip():
            raise RuntimeError(
                "The final OpenSSL Configure argument is empty"
            )

        if final_line.endswith("\r\n"):
            newline = "\r\n"
            final_line_without_newline = final_line[:-2]
        elif final_line.endswith("\n"):
            newline = "\n"
            final_line_without_newline = final_line[:-1]
        else:
            newline = "\n"
            final_line_without_newline = final_line

        indentation_match = re.match(
            r"^[ \t]*",
            final_line_without_newline,
        )
        indentation = indentation_match.group(0)

        shell_continuation = " " + "\\"

        configure_lines[command_end_index] = (
            final_line_without_newline.rstrip()
            + shell_continuation
            + newline
        )

        generated_lines = []

        for index, option in enumerate(configure_options):
            is_last_option = (
                index == len(configure_options) - 1
            )

            suffix = (
                ""
                if is_last_option
                else shell_continuation
            )

            generated_lines.append(
                f"{indentation}{option}{suffix}{newline}"
            )

        configure_lines[
            command_end_index + 1:command_end_index + 1
        ] = generated_lines

        new_configure_block = "".join(configure_lines)

        updated_text = (
            original_text[:configure_start]
            + new_configure_block
            + original_text[configure_end:]
        )

        if updated_text == original_text:
            raise RuntimeError(
                "Generated libopenssl.mk is unchanged"
            )

        original_mode = libopenssl_mk.stat().st_mode & 0o7777
        temporary_path = None

        try:
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{libopenssl_mk.name}.",
                suffix=".tmp",
                dir=libopenssl_mk.parent,
                text=True,
            )

            temporary_path = Path(temporary_name)

            with os.fdopen(
                file_descriptor,
                "w",
                encoding="utf-8",
            ) as temporary_file:
                temporary_file.write(updated_text)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.chmod(temporary_path, original_mode)
            os.replace(temporary_path, libopenssl_mk)
            temporary_path = None

        finally:
            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink()

        written_text = libopenssl_mk.read_text(
            encoding="utf-8"
        )

        for option in configure_options:
            if option not in written_text:
                raise RuntimeError(
                    f"Option was not written to libopenssl.mk: "
                    f"{option}"
                )

        print(f"Updated: {libopenssl_mk}")
        print(
            "OpenSSL options:",
            " ".join(configure_options),
        )




    def write_buildroot_hook_script_libxml2(
        self,
        ground_truth_flags,
        script_path,
        project,
    ):
        """Write a script that toggles #if 0/1 feature macros."""

        config_h = str(project.metadata.get("config_h", ""))

        with open(script_path, "w") as f:
            f.write("#!/bin/sh\n")
            f.write(f'CONFIG_H="{config_h}"\n')
            f.write('echo "Updating macros in $CONFIG_H"\n')

            for macro, value in ground_truth_flags:
                enabled = "1" if value == "True" else "0"

                f.write(
                    "sed -i "
                    f"'/^#if[[:space:]]\\+[01][[:space:]]*$/"
                    f"{{N;/\\n#define[[:space:]]\\+{macro}[[:space:]]*$/"
                    f"{{s/^#if[[:space:]]\\+[01]/#if {enabled}/;}}}}' "
                    '"$CONFIG_H"\n'
                )

        os.chmod(script_path, 0o755)