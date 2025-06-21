import yaml
from pathlib import Path
from typing import Dict, Any
from platformdirs import user_config_dir, user_data_dir

__all__ = ['get_user_config_path', 'get_user_data_path', 'deep_merge', 'BaseConfigSection']

# ─────────────────────────────────────────────────────────────────────
# CONSTANTS & HELPERS
# ─────────────────────────────────────────────────────────────────────
APP_NAME = "sora"
CONFIG_NAME = "config.yaml"


def get_user_config_path() -> Path:
    """
    Returns the path to the user's local configuration file,
    creating its parent directory if needed.
    """
    config_dir = Path(user_config_dir(APP_NAME))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / CONFIG_NAME


def get_user_data_path() -> Path:
    """
    Returns the path to the user's local configuration file,
    creating its parent directory if needed.
    """
    data_dir = Path(user_data_dir(APP_NAME))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merges two dictionaries. Values from `override` take precedence over `base`.
    """
    result = dict(base)
    for key, value in override.items():
        if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


# ─────────────────────────────────────────────────────────────────────
# BASE CONFIG SECTION
# ─────────────────────────────────────────────────────────────────────
class BaseConfigSection:
    """
    Base class for one section of the configuration.

    Each subclass should define:
      - LOCAL_KEYS: a list of attribute names that are allowed to be overridden locally.
      - _initialize(global_data, merged_data): a method that picks values from each layer.

    Public methods:
      - to_dict_common(): returns all values (global + local) for display or saving global merges.
      - to_dict_local(): returns only keys listed in LOCAL_KEYS, for writing to local file.
      - save(): calls parent.save_local() to persist local overrides.
      - __str__(): YAML-formatted string of the merged section.
    """

    LOCAL_KEYS: list[str] = []  # override in subclasses

    def __init__(self, parent: 'Config', section_name: str, global_data: dict, merged_data: dict):
        self._parent = parent
        self._section_name = section_name
        self._initialize(global_data, merged_data)

    def _initialize(self, global_data: dict, merged_data: dict):
        """
        Subclasses must implement this, picking values from:
          - global_data: the values that come only from the packaged default.
          - merged_data: the result of deep_merge(global_data, local_data).
        """
        raise NotImplementedError

    def to_dict_common(self) -> Dict[str, Any]:
        """
        Returns a dictionary of **all public attributes** (global + local) for merged display.
        """

        def serialize(value):
            if isinstance(value, BaseConfigSection):
                return value.to_dict_common()
            elif isinstance(value, dict):
                return {k: serialize(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [serialize(v) for v in value]
            else:
                return value

        return {
            key: serialize(val)
            for key, val in self.__dict__.items()
            if not key.startswith('_')
        }

    def to_dict_local(self) -> Dict[str, Any]:
        """
        Returns a dictionary of only the keys in LOCAL_KEYS, for writing to local config.
        """
        result: dict[str, Any] = {}
        for key in self.LOCAL_KEYS:
            if hasattr(self, key):
                val = getattr(self, key)
                # If nested BaseConfigSection, call its to_dict_local
                if isinstance(val, BaseConfigSection):
                    nested = val.to_dict_local()
                    if nested:
                        result[key] = nested
                else:
                    result[key] = val
        return result

    def save(self):
        """
        Triggers saving of local overrides across all sections.
        """
        self._parent.save_local()

    def __repr__(self):
        return f"<{self.__class__.__name__}({self.to_dict_common()})>"

    def __str__(self):
        return yaml.dump(self.to_dict_common(), sort_keys=False, default_flow_style=False)
