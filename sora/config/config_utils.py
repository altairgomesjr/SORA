import yaml
from pathlib import Path
from pydantic import BaseModel, ValidationError

class GeneralConfig(BaseModel):
    project_name: str
    output_directory: str

class LoggingConfig(BaseModel):
    level: str
    log_to_file: bool
    file_path: str

class FullConfig(BaseModel):
    general: GeneralConfig
    logging: LoggingConfig

def load_and_validate_config(path: Path) -> FullConfig:
    with open(path, "r") as f:
        raw = yaml.safe_load(f)
    return FullConfig(**raw)
