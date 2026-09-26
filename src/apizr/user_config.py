"""Explicit operator preferences; never repository-granted permissions."""

import json
import tomllib
from pathlib import Path
from typing import Literal

from apizr.capabilities.types import ValueModel
from apizr.config_files import read_regular
from apizr.local_plugins.models import PluginError
from apizr.project import ProjectConfig

MAX_USER_CONFIG_BYTES = 65536


class UserConfig(ValueModel):
    schema_version: Literal["apizr.user/v1"]
    plugins_dir: Path | None = None


def load_user_config(path: Path) -> UserConfig:
    try:
        data = tomllib.loads(read_regular(path, MAX_USER_CONFIG_BYTES).decode("utf-8"))
        config = UserConfig.model_validate_json(json.dumps(data), strict=True)
        if config.plugins_dir is not None:
            ProjectConfig.local_paths(str(config.plugins_dir))
            return config.model_copy(
                update={"plugins_dir": path.absolute().parent / config.plugins_dir}
            )
        return config
    except (OSError, ValueError, TypeError, RecursionError):
        raise PluginError("invalid_user_config") from None


def plugins_directory(explicit: Path | None, user_config: Path | None) -> Path | None:
    # Validate an explicitly requested file even when overridden by a CLI option.
    config = load_user_config(user_config) if user_config is not None else None
    return explicit if explicit is not None else config.plugins_dir if config else None
