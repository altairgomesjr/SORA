import logging
from .core import Config
from pathlib import Path

def configure_logger():
    """
    Reads LoggingConfig from Config and reconfigures the module‐level logger accordingly.
    """
    cfg = Config()  # this loads global + local, merges them
    log_cfg = cfg.logging

    # Set logger level (you could also pull level from another section)
    root = logging.getLogger()  # or your module's logger
    root.setLevel(logging.DEBUG)  # or any default you'd like

    # Remove any old file handlers to avoid duplicates
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler):
            root.removeHandler(h)

    formatter_debug = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    formatter_user_file = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    formatter_user_console = logging.Formatter("%(levelname)s - %(message)s")

    log_debug_path = Path(log_cfg.log_debug_path)
    log_debug_path.parent.mkdir(parents=True, exist_ok=True)
    mode = 'w' if log_cfg.overwrite_debug_file else 'a'

    fhd = logging.FileHandler(log_debug_path, encoding='utf-8', mode=mode)
    fhd.setLevel(logging.DEBUG)
    fhd.setFormatter(formatter_debug)
    root.addHandler(fhd)

    if log_cfg.log_to_console:
        ch = logging.StreamHandler()
        ch.setLevel(log_cfg.log_level)
        ch.setFormatter(formatter_user_console)
        root.addHandler(ch)

    if log_cfg.log_to_file:
        # Ensure parent directory exists
        log_path = Path(log_cfg.log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        mode = 'w' if log_cfg.overwrite_log_file else 'a'

        fh = logging.FileHandler(log_path, encoding='utf-8', mode=mode)
        fh.setLevel(log_cfg.log_level)
        fh.setFormatter(formatter_user_file)
        root.addHandler(fh)
        logging.info(f"Log file is: {log_path.absolute()}")

    logging.info(f"Debug log file is: {log_debug_path.absolute()}")
    logging.debug(f"Full merged config:\n{cfg}")