import subprocess

class InformationExtractor:
    """
    Class to get the low hanging fruit infromation from the binary.
    """
    def __init__(self, file_path: str):
        self.strings = run_strings(file_path)
        self.metadata: list[str] = []

def run_strings(path: str, min_length: int = 3) -> list[str]:
    result = subprocess.run(
        ["strings", f"-n{min_length}", path],
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout.splitlines()

    