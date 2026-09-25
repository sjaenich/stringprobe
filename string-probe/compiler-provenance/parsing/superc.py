import os
import sys
from pathlib import Path
from shutil import which
import subprocess
from .presence_condition import PresenceCondition


def write_content_to_file(filepath: str, content: str):
    with open(filepath, 'w') as f:
        f.write(content)

def run(args, stdin=None, capture_stdout=True, capture_stderr=True, cwd=None, timeout=None, shell=False):
  """Helper for running an external process.
  Returns a tuple of (stdout, stderr, return_code, time_elapsed) for the process.
  Arguments:
  args -- args, a list to pass to subprocess.Popen.
  stdin -- The content to be passed as stdin to the process.
  capture_stdout -- If set, capture stdout to be returned by the method. Otherwise, keep it at stdout.
  capture_stderr -- If set, capture stderr to be returned by the method. Otherwise, keep it at stdin.
  cwd -- Current working directory for the process.
  timeout -- timeout in seconds. If expires, raises an subprocess.TimeoutExpired exception.
  """
  import subprocess
  import time
  stdout_param = subprocess.PIPE if capture_stdout else None
  stderr_param = subprocess.PIPE if capture_stderr else None
  time_start = time.time()
  env = os.environ.copy()

  env["JAVA_DEV_ROOT"] = "/workspaces/RevEng/Tools/superc/"

  env["CLASSPATH"] = (
      f"{env.get('CLASSPATH', '')}:"
      f"{env['JAVA_DEV_ROOT']}/classes:"
      f"{env['JAVA_DEV_ROOT']}/bin/junit.jar:"
      f"{env['JAVA_DEV_ROOT']}/bin/antlr.jar:"
      f"{env['JAVA_DEV_ROOT']}/bin/javabdd.jar:"
      f"{env['JAVA_DEV_ROOT']}/bin/json-simple-1.1.1.jar:"
      "/usr/share/java/org.sat4j.core.jar:"
      "/usr/share/java/com.microsoft.z3.jar:"
      "/usr/share/java/json-lib.jar"
  )

  env["JAVA_ARGS"] = "-Xms2048m -Xmx4048m -Xss128m"
  env["JAVA_HOME"] = "/usr/lib/jvm/java-8-openjdk-amd64/"
  popen = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, shell=shell, env=env)
  if stdin != None: popen.stdin.write(stdin)
  captured_stdout, captured_stderr = popen.communicate(timeout=timeout)
  time_elapsed = time.time() - time_start
  popen.stdin.close()
  return captured_stdout, captured_stderr, popen.returncode, time_elapsed

class BasicLogger:
  """A simple logger."""
  def __init__(self, quiet=False, verbose=False, flush=True):
    assert (not (quiet and verbose))
    self.quiet = quiet
    self.verbose = verbose
    self.flush = flush
  
  def __flush(self):
    if self.flush: sys.stderr.flush()

  def info(self, msg):
    if not self.quiet:
      sys.stderr.write("INFO: %s" % msg)
      self.__flush()
    
  def warning(self, msg):
    sys.stderr.write("WARNING: %s" % msg)
    self.__flush()
    
  def error(self, msg):
    sys.stderr.write("ERROR: %s" % msg)
    self.__flush()
    
  def debug(self, msg):
    if self.verbose:
      sys.stderr.write("DEBUG: %s" % msg)
      self.__flush()



class SuperC:
  class SuperC_Exception(Exception):
    pass
  class SuperC_ChecksFailed(SuperC_Exception):
    def __init__(self, reason):
      self.reason = reason
      super().__init__(self.reason)

  def __init__(self, logger = BasicLogger()):
    """Arguments:
    * superc_linux_script_path -- SuperC linux script, which is found at
    superc/scripts/superc_linux.sh, where superc/ is the top SuperC source
    directory. Searches "superc_linux.sh" in PATH by default.
    """
    self.logger = logger
  
    self.__check_superc()
  
  def __check_superc(self):
    """Check and whether SuperC can be used for getting sourceline presence
    conditions for Linux files.
    
    Returns on success.
    Raises SuperC_ChecksFailed exception on error.

    Followings checks are done:
    * java exists
    * java runs
    * SuperC runs
    * SuperC -sourcelinePC runs
    """
    def is_success(command_to_run: list):
      return 0 == run(command_to_run, capture_stdout=True, capture_stderr=True)[2]
    
    self.logger.debug("Starting SuperC checks.\n")

    if not which("java"):
      raise SuperC.SuperC_ChecksFailed("java could not be found")

    cmd = ["java", "--help"]
    if not is_success(cmd):
      raise SuperC.SuperC_ChecksFailed("Running java (\"%s\") failed" % " ".join(cmd))

    cmd = ["java", "superc.SuperC"]
    if not is_success(cmd):
      raise SuperC.SuperC_ChecksFailed("Running SuperC (\"%s\") failed" % " ".join(cmd))

    cmd = ["java", "superc.SuperC", "-sourcelinePC", os.devnull, os.devnull]
    if not is_success(cmd):
      raise SuperC.SuperC_ChecksFailed("Running SuperC -sourcelinePC (\"%s\") failed" % " ".join(cmd))
    self.logger.debug("SuperC checks passed.\n")
    return True


  def get_pc_and_macro_values(self, srcfile_path: Path, library_dir: str, line_number: int|None, macro: str| None, config_h = None, name = None, include_dir = None, extra_include=None) -> list[PresenceCondition]:
      """
      Get the presence conditions of a line number and if applicable  the Macro value 
      """
      print("SuperC this is the free header file", config_h)

      srcfile = srcfile_path.stem

      
      if macro is not None:
        pc_file_path = "/workspaces/RevEng/superc_output/output_" + name + "_" + macro + "_" + str(srcfile) + ".txt"
        if line_number is not None:
          pc_file_path = "/workspaces/RevEng/superc_output/output_" + name + "_" + macro + "_" + str(srcfile) + "_" + str(line_number) + ".txt"
      else:
        pc_file_path = "/workspaces/RevEng/superc_output/output_" + name + "_" + str(srcfile) + ".txt"
      self.logger.debug("Presence conditions file will be created at \"%s\".\n" % pc_file_path)
      pc_file_path_check = pc_file_path
 

      
      pc_file_path += ":" + str(line_number)
      if macro:
        pc_file_path += ":" + macro 
      superc_flags = "-sourcelinePC"
      include_flags = "-I"
      include = str(include_dir)
      extra_include_flag = "-I"
      if extra_include == "":
        extra_include = str(include_dir)

      mock_header ="-include"
      mock_header_location = "/workspaces/RevEng/header/other_defines/other_defines_" + name + ".h"
      if line_number is None:
        pc_file_path = "/workspaces/RevEng/all_strings/all_strings_" + name + "_" + str(srcfile) + ".txt"
        pc_file_path_check = pc_file_path
      superc_sourcelinepc_cmd = ["java", "superc.SuperC", "-restrictFreeToHeader", str(config_h), mock_header, mock_header_location, include_flags, include, extra_include_flag, str(extra_include),  "-I", "/workspaces/RevEng/buildroot-2025.02.4/output/host/lib/gcc/arm-buildroot-linux-gnueabihf/13.3.0/include", "%s" % superc_flags, pc_file_path, str(srcfile_path)]
  
      print("Running SuperC with command:", superc_sourcelinepc_cmd)
      if not os.path.isfile(pc_file_path_check):
        try:
          self.logger.debug("Running SuperC sourcelinePC.\n")
          out, err, ret, time_elapsed = run(superc_sourcelinepc_cmd, cwd=library_dir)
          print(out,err,ret)
          self.logger.debug("Finished running SuperC sourcelinePC.\n") 
          
          if not os.path.isfile(pc_file_path_check):
            self.logger.debug("SuperC failed to create presence conditions file at \"%s\".\n" % pc_file_path)
            print("This should no happen")
            return None
        except subprocess.TimeoutExpired:
          return None
      else:
        print("Presence conditions file already exists at \"%s\". Skipping SuperC execution.\n" % pc_file_path_check)
      with open(pc_file_path_check, 'r') as f:
        entries = []
        for line in f:
          line = line.strip()
          if not line.startswith("{"):
            continue
          entry = PresenceCondition()
          entry.parse(line)
          entries.append(entry)
      return entries

      