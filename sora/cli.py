import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from importlib import resources, metadata
import logging

# from .config.logging import configure_logger
from .config.config_utils import load_and_validate_config

logger = logging.getLogger("sora.cli")

def copy_resources(src_pkg: str, target_dir: Path, suffix: str, overwrite: bool):
    pkg_dir = resources.files(src_pkg)
    for item in pkg_dir.iterdir():
        # only files matching our suffix
        if not item.is_file() or Path(item.name).suffix != suffix:
            continue

        target_path = target_dir / item.name
        if target_path.exists() and not overwrite:
            logger.warning(f"Skipped (already exists): {item.name}")
            continue

        # read from package resource and write to disk
        data = item.read_bytes()
        target_path.write_bytes(data)
        logger.info(f"Copied: {item.name}")

def start_jupyterlab(overwrite=False):
    logger.info("Setting up Jupyter notebooks…")
    copy_resources("sora.data.notebooks", Path.cwd(), ".ipynb", overwrite)
    logger.info("Launching JupyterLab…")
    proc = subprocess.Popen(["jupyter", "lab", str(Path.cwd())])
    try:
        proc.wait()
    except KeyboardInterrupt:
        logger.info("Interrupt received, shutting down JupyterLab…")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        logger.info("JupyterLab stopped.")

def start_config_templates(overwrite=False):
    logger.info("Setting up configuration templates…")
    copy_resources("sora.data.config", Path.cwd(), ".yaml", overwrite)

def run_from_config(config_path: str, check_only: bool):
    path = Path(config_path)
    logger.info(f"{'Checking' if check_only else 'Loading'} config: {path}")
    try:
        config = load_and_validate_config(path)
        logger.info("Configuration is valid.")
        if check_only:
            return
        # ─── Insert your “real” pipeline or runner here ───
        logger.info(f"Running SORA pipeline for project “{config.general.project_name}”")
        # e.g. run_pipeline(config)
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

def cmd_version():
    try:
        ver = metadata.version("sora-astro")
    except metadata.PackageNotFoundError:
        ver = "unknown"
    print(ver)

def cmd_update():
    logger.info("Updating SORA package via pip…")
    # Use the current Python interpreter to upgrade
    res = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "sora-astro"])
    if res.returncode == 0:
        logger.info("SORA successfully updated.")
    else:
        logger.error("Update failed (see pip output above).")
        sys.exit(res.returncode)

def main():
    parser = argparse.ArgumentParser(prog="sora", description="SORA CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # start
    sp = subparsers.add_parser("start", help="Initialize helper files")
    sp.add_argument("what", choices=["jupyter", "config"], help="What to start")
    sp.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
    sp.add_argument("--verbose", action="store_true", help="Enable debug logging")

    # run
    rp = subparsers.add_parser("run", help="Run SORA with a YAML config")
    rp.add_argument("config", help="Path to the YAML config file")
    rp.add_argument("--check", action="store_true", help="Validate and exit without running")

    # version
    subparsers.add_parser("version", help="Show installed SORA version")

    # update
    subparsers.add_parser("update", help="Upgrade SORA to the latest version via pip")

    args = parser.parse_args()

    # configure logging (if applicable)
    # configure_logger()

    if args.command == "start":
        if args.what == "jupyter":
            start_jupyterlab(overwrite=args.overwrite)
        else:
            start_config_templates(overwrite=args.overwrite)

    elif args.command == "run":
        run_from_config(args.config, check_only=args.check)

    elif args.command == "version":
        cmd_version()

    elif args.command == "update":
        cmd_update()

if __name__ == "__main__":
    main()
