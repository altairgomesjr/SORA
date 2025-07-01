import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from importlib import resources, metadata
import logging
import questionary

from sora.config.core import Config
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

def interactive_config(mode: str = "basic"):
    level = {'basic': 1, 'advanced': 2, 'develop': 3}[mode]
    cfg = Config()
    schema = cfg.get_prompt_schema()
    section_names = list(schema.keys())

    logging.info(f"Configuring in '{mode}' mode.")
    # 1) Choose section to edit
    section_choice = questionary.select(
        "Which section would you like to edit?",
        choices=["All sections"] + section_names + ["Load Databases", "Exit"]
    ).ask()

    if section_choice in (None, "Exit"):
        logging.warning("Configuration aborted.")
        return

    to_edit = section_names if section_choice == "All sections" else [section_choice]

    for sec_name in to_edit:
        if sec_name == "Load Databases":
            continue
        section = getattr(cfg, sec_name)
        props = schema[sec_name]
        print(f"── {sec_name.upper()} ──")
        logging.debug(f"Editing section {sec_name} via CLI")

        for key, meta in props.items():
            key_level = meta.get('level', 1)
            if key_level > level:
                continue  # skip advanced/develop keys in basic, develop keys in advanced

            question = meta['question']
            current = getattr(section, key)

            if 'choices' in meta:
                # Build select choices with a "keep current" option
                keep_label = f"Keep current ({current})"
                choices = [keep_label] + meta['choices']
                answer = questionary.select(
                    f"{question}",
                    choices=choices,
                    default=keep_label
                ).ask()

                if answer is None or answer == keep_label:
                    # user chose to keep current
                    continue
                new_value = answer

            else:
                # Text prompt: show current in the question, leave default blank
                answer = questionary.text(
                    f"{question} (current: {current})",
                    default=""
                ).ask()

                if answer is None or answer.strip() == "":
                    continue  # keep current
                # Convert numeric if needed
                if isinstance(current, bool):
                    new_value = answer.lower() in ("y", "yes", "true", "1")
                elif isinstance(current, int):
                    new_value = int(answer)
                elif isinstance(current, float):
                    new_value = float(answer)
                else:
                    new_value = answer

            # Finally, apply the update
            cfg.update(sec_name, key, new_value)
            print(f"→ {sec_name}.{key} set to {new_value}")

    if section_choice in ["All sections", "Load Databases"]:
        print(f"── LOAD DATABASES ──")
        answer = questionary.confirm('Would you like to download (or update) the DAMIT tables now?').ask()
        if answer:
            from sora.body.damit.damit_database import DamitDB
            db = DamitDB()
            db.update_database(force=True)
        answer = questionary.confirm('Would you like to download (or update) the NIMA tables now?').ask()
        if answer:
            from sora.ephem.nima import NimaDB
            db = NimaDB()
            db.update_database(force=True)

    logging.info("Configuration updated!")

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

    # config
    cp = subparsers.add_parser("config", help="Interactively create or update SORA configuration")
    cp.add_argument("mode", default="basic", choices=["basic", "advanced"], help="Level of configuration", nargs='?')

    # dev
    dev = subparsers.add_parser("dev", help="Developer utilities namespace")
    dev_sub = dev.add_subparsers(dest="dev_command", required=True)
    dev_sub.add_parser("config", help="Configuration at developer level")

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

    elif args.command == "config":
        interactive_config(mode=args.mode)

    elif args.command == "dev":
        if args.dev_command == "config":
            interactive_config(mode="develop")

    elif args.command == "version":
        cmd_version()

    elif args.command == "update":
        cmd_update()

if __name__ == "__main__":
    main()
