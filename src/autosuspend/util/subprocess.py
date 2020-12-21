import subprocess

from ..checks import SevereCheckError


def raise_severe_if_command_not_found(error: subprocess.CalledProcessError) -> None:
    if error.returncode == 127:
        # see http://tldp.org/LDP/abs/html/exitcodes.html
        raise SevereCheckError(f"Command '{' '.join(error.cmd)}' does not exist")
