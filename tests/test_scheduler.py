import os
import pathlib
import sys
from unittest.mock import patch


def test_scheduler_config_parsing():
    """Verify scheduler argument parsing works (defaults and custom values)."""
    test_args = ["scheduler.py", "--config", "my_config.yaml", "--at", "14:30"]
    with patch.object(sys, "argv", test_args):
        with patch("src.scheduler.run_scheduler") as mock_run:
            from src.scheduler import main
            main()
            mock_run.assert_called_once_with("my_config.yaml", "14:30")


def test_run_sh_exists_and_executable():
    """Verify run.sh exists and has execute permission."""
    run_sh = pathlib.Path(__file__).parent.parent / "run.sh"
    assert run_sh.is_file(), f"run.sh not found at {run_sh}"
    assert os.access(str(run_sh), os.X_OK), f"run.sh is not executable"
