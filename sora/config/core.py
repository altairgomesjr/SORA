import yaml
import shutil
from pathlib import Path
from typing import Dict, Any
from .meta import BaseConfigSection, get_user_config_path, get_user_data_path, deep_merge


# ─────────────────────────────────────────────────────────────────────
# SECTION CLASSES (with LOCAL_KEYS and _initialize implementations)
# ─────────────────────────────────────────────────────────────────────
class LoggingConfig(BaseConfigSection):
    LOCAL_KEYS = ['log_to_debug', 'log_debug_path', 'overwrite_debug_file', 'log_to_file', 'log_to_console',
                  'log_level', 'log_file_path', 'log_file_path', 'overwrite_log_file']

    # Metadata for interactive prompts
    PROMPTS = {
        'log_to_debug': {'question': "Save debug log to a file?", 'level': 3},
        'log_debug_path': {'question': "File to save debug logs to:", 'level': 3},
        'overwrite_debug_file': {'question': "Overwrite debug file log when starting SORA?", 'level': 2},

        'log_to_file': {'question': "Save log to a file?", 'level': 1},
        'log_file_path': {'question': "File to save logs to:", 'level': 2},
        'overwrite_log_file': {'question': "Overwrite file log when starting SORA?", 'level': 1},
        'log_to_console': {'question': "Show log to console?", 'level': 1},
        'log_level': {
            'question': "Log level:", 'level': 2,
            'choices': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        }
    }

    def _initialize(self, global_data: dict, merged_data: dict):
        self.log_to_debug = merged_data.get('log_to_debug', True)
        self.log_debug_path = merged_data.get('log_debug_path', './logs/sora_debug.log')
        self.overwrite_debug_file = merged_data.get('overwrite_debug_file', False)

        self.log_to_file = merged_data.get('log_to_file', True)
        self.log_to_console = merged_data.get('log_to_console', True)
        self.log_level = merged_data.get('log_level', 'INFO')
        self.log_file_path = merged_data.get('log_file_path', './logs/sora.log')
        self.overwrite_log_file = merged_data.get('overwrite_log_file', False)


class DamitConfig(BaseConfigSection):
    LOCAL_KEYS = ['update_age_days']

    # Metadata for interactive prompts
    PROMPTS = {
        'database': {'question': "Database file:", 'level': 3},
        'json_data': {'question': "JSON Meta file:", 'level': 3},
        'data_dir': {'question': "Directory to save DAMIT 3D models:", 'level': 3},
        'update_age_days': {'question': "Maximum number of days between automatic updates:", 'level': 1},
    }

    def _initialize(self, global_data: dict, merged_data: dict):
        self.database = global_data.get('database', 'damit.db')
        self.json_data = global_data.get('json_data', 'damit_meta.json')
        self.data_dir = global_data.get('data_dir', 'models')
        self.update_age_days = merged_data.get('update_age_days', 20)


class NimaConfig(BaseConfigSection):
    LOCAL_KEYS = ['update_age_days']

    # Metadata for interactive prompts
    PROMPTS = {
        'database': {'question': "Database file:", 'level': 3},
        'json_data': {'question': "JSON file:", 'level': 3},
        'data_dir': {'question': "Directory to save NIMA kernels:", 'level': 3},
        'update_age_days': {'question': "Maximum number of days between automatic updates:", 'level': 1},
    }

    def _initialize(self, global_data: dict, merged_data: dict):
        self.database = global_data.get('database', 'nima.db')
        self.json_data = global_data.get('json_data', 'nima_meta.json')
        self.data_dir = global_data.get('data_dir', 'kernels/nima')
        self.update_age_days = merged_data.get('update_age_days', 30)

class EphemConfig(BaseConfigSection):
    LOCAL_KEYS = []

    PROMPTS = {}

    def _initialize(self, global_data: dict, merged_data: dict):
        self.planet_kernels = global_data.get('planet_kernels', 'planetary_kernels.json')
        self.data_dir = global_data.get('data_dir', 'kernels/planetary')
        self.planetary_default = merged_data.get('planetary_default', 'DE440')

# ─────────────────────────────────────────────────────────────────────
# CONFIG CLASS (Singleton, Layered Global+Local)
# ─────────────────────────────────────────────────────────────────────
class Config:
    """
    Top-level configuration manager with a two-layer approach:
      1. Global config: packaged default (default_config.yaml)
      2. Local config: user overrides (~/.config/sora/config.yaml)

    Only keys listed in LOCAL_KEYS for each section are saved locally.
    """
    _instance = None

    def __new__(cls, global_path: Path = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_config(global_path)
        return cls._instance

    def _init_config(self, global_path: Path = None):
        # 1) Determine paths
        self._global_path = Path(global_path) if global_path else (Path(__file__).parent / 'default_config.yaml')
        self._local_path = get_user_config_path()
        self._data_path = get_user_data_path()

        # 2) Load global config
        if not self._global_path.exists():
            raise FileNotFoundError(f"Global config not found at {self._global_path}")
        global_data = self._load_yaml(self._global_path)

        # 3) Load or create local config
        if not self._local_path.exists():
            self._local_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(self._global_path, self._local_path)
        local_data = self._load_yaml(self._local_path)
        # Create data path
        if not self._data_path.exists():
            self._data_path.parent.mkdir(parents=True, exist_ok=True)

        # 4) Merge (local overrides global)
        merged_data = deep_merge(global_data, local_data)

        # 5) Initialize each section with (global_data_section, merged_data_section)
        self.logging = LoggingConfig(self, 'logging',
                                     global_data.get('logging', {}),
                                     merged_data.get('logging', {}))

        self.damit = DamitConfig(self, 'damit',
                                 global_data.get('damit', {}),
                                 merged_data.get('damit', {}))

        self.nima = NimaConfig(self, 'nima',
                               global_data.get('nima', {}),
                               merged_data.get('nima', {}))

        self.ephem = EphemConfig(self, 'ephem',
                                 global_data.get('ephem', {}),
                                 merged_data.get('ephem', {}))

        #logger.info(f"Configuration loaded (global: {self._global_path}, local: {self._local_path})")

    def get_prompt_schema(self):
        """
        Returns a dict:
          { section_name: { key: meta_dict, … }, … }
        but only for sections with PROMPTS defined.
        """
        schema = {}
        for sec_name in ['logging', 'damit', 'nima', 'ephem']:
            section = getattr(self, sec_name, None)
            meta = getattr(section.__class__, 'PROMPTS', None)
            if section is not None and meta:
                schema[sec_name] = meta
        return schema

    @property
    def config_path(self) -> Path:
        return self._local_path

    @property
    def data_path(self) -> Path:
        return self._data_path

    def _load_yaml(self, path: Path) -> dict:
        with open(path, 'r') as f:
            return yaml.safe_load(f) or {}

    def to_dict(self) -> Dict[str, Any]:
        """
        Returns the merged (global + local) configuration as a dictionary.
        """
        return {
            'logging': self.logging.to_dict_common(),
            'damit': self.damit.to_dict_common(),
            'nima': self.nima.to_dict_common(),
            'ephem': self.ephem.to_dict_common(),
        }

    def to_local_dict(self) -> Dict[str, Any]:
        """
        Returns only the local overrides as a dictionary, for saving to the local file.
        Sections without any overrides will be omitted.
        """
        data: Dict[str, Any] = {}
        for section_name, section_obj in [
            ('logging', self.logging),
            ('damit', self.damit),
            ('nima', self.nima),
            ('ephem', self.ephem),
        ]:
            local_section = section_obj.to_dict_local()
            if local_section:  # only include sections that have local overrides
                data[section_name] = local_section
        return data

    def save_local(self):
        """
        Writes only the local override settings to the local config file.
        """
        local_data = self.to_local_dict()
        with open(self._local_path, 'w') as f:
            yaml.dump(local_data, f, sort_keys=False)

    # Alias so section.save() can just call config.save()
    save = save_local

    def update(self, section: str, key: str, value: Any):
        """
        Update a local-overridable key in a given section and persist it locally.
        Raises KeyError if the key is not in that section's LOCAL_KEYS.
        """
        section_obj = getattr(self, section, None)
        if section_obj and key in section_obj.LOCAL_KEYS:
            setattr(section_obj, key, value)
            self.save_local()
        else:
            raise KeyError(f"Cannot update '{section}.{key}'; it may not be user-overridable.")

    def __str__(self) -> str:
        """
        Returns the merged configuration as a YAML-formatted string.
        """
        return yaml.dump(self.to_dict(), sort_keys=False, default_flow_style=False)

    def __repr__(self) -> str:
        return f"<Config(global={self._global_path}, local={self._local_path})>"
