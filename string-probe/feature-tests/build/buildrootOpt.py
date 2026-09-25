from .buildroot import BuildrootBuildManager
from pathlib import Path
from .buildroot import *

class BuildrootOpt(BuildrootBuildManager):
    def __init__(self, buildroot_dir, output_base, timeout = 300):
        super().__init__(buildroot_dir, output_base, timeout)
        self.optimization_level: str = "O0"

    def build(self, project: Project, gt: GroundTruthExtractor, iteration=None) -> BuildResult:
        pkg = project.name
        buildroot_dir = self.buildroot_dir
        if iteration == 1:
            self.buildroot_dir = Path("/workspaces/RevEng/buildroot-opt/")
        
        out_dir = self.buildroot_dir / "output/build/"
        log_file = out_dir / Path("buildroot_" + pkg + ".log")

        start = time.time()

        config = project.metadata["config_h"]
        relative = config.relative_to(buildroot_dir)

        binary = project.metadata["binary"]
        relative_b = binary.relative_to(buildroot_dir)

        project.metadata["config_h"] = self.buildroot_dir / relative
        project.metadata["binary"] = self.buildroot_dir / relative_b
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
        env["MY_REAL_COMPILER"] = "/workspaces/RevEng/buildroot-2025.02.4/output/host/bin/gcc-13.real"
        env["MY_EXTRA_FLAGS"] = gt.mix_cflags(project)
        env["SOURCE_DATE_EPOCH"] = "1704067200"

        res = self._run(cmd, self.buildroot_dir, log_file, env)
        success = res.returncode == 0

        project.metadata["config_h"] = config

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

        binaries = [project.metadata["binary"], dst_binary]
        duration = time.time() - start
        project.metadata["binary"] = binary
        with log_file.open("a") as f:
            f.write(f"\n=== BUILD TIME: {duration:.2f}s ===\n")

        print(f"Build completed in {duration:.2f} seconds. Success: {success}. Binaries: {binaries}")
        self.buildroot_dir = buildroot_dir

        return BuildResult(
            success=success,
            log_file=log_file,
            binary_paths=binaries,
            error="Rebuild Macros" if not success and iteration > 1 else None,
        )



    
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

        buildroot_dir = Path(self.buildroot_dir)

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
