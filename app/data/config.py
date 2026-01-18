"""
ConfigManager - YAML configuration management

Handles loading, saving, validation, and provides dot-notation
access to nested configuration values.
"""

import yaml
from pathlib import Path
from typing import Any, Optional, List, Dict
import logging
import copy
import tempfile

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Manages application configuration in YAML format.

    Handles loading, saving, validation, and provides
    dot-notation access to nested config values.
    """

    DEFAULT_CONFIG = {
        'app': {
            'autostart': False,
            'minimize_to_tray': True,
            'show_notifications': True,
        },
        'hotkey': {
            'primary': 'ctrl+space',
            'fallback': 'ctrl+shift+v',
        },
        'whisper': {
            'model': 'small',
            'language': None,
            'device': 'cuda',
            'fp16': True,
            'beam_size': 1,
            'temperature': 0.0,
        },
        'audio': {
            'device': None,
            'sample_rate': 16000,
            'noise_reduction': False,
            'vad_enabled': False,
        },
        'overlay': {
            'enabled': True,
            'position': 'top-center',
            'monitor': 0,
            'auto_dismiss_ms': 2500,
        },
        'ui': {
            'theme': 'dark',
            'history_limit': 50,
            'font_size': 14,
        },
        'storage': {
            'database_path': '~/.config/whisper-free/history.db',
            'retention_days': 30,
            'save_audio_files': False,
        },
    }

    # Valid values for validation
    VALID_MODELS = ['tiny', 'base', 'small', 'medium', 'large-v3-turbo']
    VALID_POSITIONS = ['top-center', 'top-left', 'top-right', 'bottom-center']

    def __init__(self, config_path: str = "~/.config/whisper-free/config.yaml"):
        """
        Initialize configuration manager.

        Args:
            config_path: Path to YAML config file

        Loads existing config or creates default if missing.
        """
        self.config_path = Path(config_path).expanduser()
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initializing config at {self.config_path}")

        # Load configuration
        self.config = self._load_config()

        # Validate on load (log warnings but continue)
        errors = self.validate()
        if errors:
            logger.warning(f"Configuration validation errors: {errors}")

    def _load_config(self) -> Dict[str, Any]:
        """
        Load configuration from YAML file.

        Returns:
            Configuration dictionary

        Creates default config if file doesn't exist.
        Merges with defaults if some keys are missing.
        """
        if not self.config_path.exists():
            logger.info("Config file not found, creating default")
            config = copy.deepcopy(self.DEFAULT_CONFIG)
            self._save_config(config)
            return config

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded_config = yaml.safe_load(f) or {}

            logger.info("Config file loaded successfully")

            # Merge with defaults (fill in missing keys)
            config = self._merge_with_defaults(loaded_config)
            return config

        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error: {e}")
            logger.warning("Using default configuration due to parse error")
            return copy.deepcopy(self.DEFAULT_CONFIG)

        except IOError as e:
            logger.error(f"Error reading config file: {e}")
            logger.warning("Using default configuration")
            return copy.deepcopy(self.DEFAULT_CONFIG)

    def _merge_with_defaults(self, user_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively merge user config with defaults.

        Args:
            user_config: User-provided configuration

        Returns:
            Merged configuration with all default keys filled in
        """
        def recursive_merge(defaults: Dict, user: Dict) -> Dict:
            """Recursively merge two dictionaries."""
            result = copy.deepcopy(defaults)

            for key, value in user.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = recursive_merge(result[key], value)
                else:
                    result[key] = value

            return result

        return recursive_merge(self.DEFAULT_CONFIG, user_config)

    def _save_config(self, config: Dict[str, Any]) -> None:
        """
        Internal method to save config to file.

        Args:
            config: Configuration dictionary to save
        """
        try:
            # Atomic write: write to temp file, then rename
            temp_fd, temp_path = tempfile.mkstemp(
                dir=self.config_path.parent,
                prefix='.config_',
                suffix='.yaml.tmp'
            )

            with open(temp_fd, 'w', encoding='utf-8') as f:
                yaml.safe_dump(
                    config,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True
                )

            # Atomic rename
            Path(temp_path).rename(self.config_path)

            logger.info(f"Config saved to {self.config_path}")

        except (IOError, OSError) as e:
            logger.error(f"Error saving config: {e}")
            raise RuntimeError(f"Failed to save configuration: {e}")

    def save(self) -> None:
        """
        Save current configuration to YAML file.

        Uses atomic write (write to temp, then rename)
        to prevent corruption on crash.
        """
        self._save_config(self.config)

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get config value using dot-notation path.

        Args:
            key_path: Dot-separated path (e.g., 'whisper.model')
            default: Value to return if key not found

        Returns:
            Config value or default

        Examples:
            config.get('whisper.model')  # Returns 'small'
            config.get('whisper.gpu_index', 0)  # Returns 0 (default)
        """
        try:
            keys = key_path.split('.')
            value = self.config

            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default

            return value

        except Exception as e:
            logger.warning(f"Error getting config key '{key_path}': {e}")
            return default

    def set(self, key_path: str, value: Any) -> None:
        """
        Set config value using dot-notation path.

        Args:
            key_path: Dot-separated path
            value: Value to set

        Creates intermediate dicts if needed.

        Examples:
            config.set('whisper.model', 'medium')
            config.set('ui.theme', 'darker')
        """
        try:
            keys = key_path.split('.')
            current = self.config

            # Navigate to parent of target key
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                elif not isinstance(current[key], dict):
                    # Can't navigate through non-dict value
                    logger.error(f"Cannot set '{key_path}': '{key}' is not a dict")
                    return

                current = current[key]

            # Set the final key
            final_key = keys[-1]
            current[final_key] = value

            logger.debug(f"Set config '{key_path}' = {value}")

        except Exception as e:
            logger.error(f"Error setting config key '{key_path}': {e}")

    def validate(self) -> List[str]:
        """
        Validate all configuration values.

        Returns:
            List of validation error messages (empty if valid)

        Checks:
            - whisper.model in valid models
            - audio.sample_rate == 16000
            - overlay.position in valid positions
            - ui.history_limit > 0
            - numeric values are correct type
        """
        errors = []

        # Validate whisper.model
        model = self.get('whisper.model')
        if model not in self.VALID_MODELS:
            errors.append(
                f"whisper.model '{model}' not in valid models: {self.VALID_MODELS}"
            )

        # Validate audio.sample_rate (Whisper requirement)
        sample_rate = self.get('audio.sample_rate')
        if sample_rate != 16000:
            errors.append(
                f"audio.sample_rate must be 16000 (Whisper requirement), got {sample_rate}"
            )

        # Validate overlay.position
        position = self.get('overlay.position')
        if position not in self.VALID_POSITIONS:
            errors.append(
                f"overlay.position '{position}' not in valid positions: {self.VALID_POSITIONS}"
            )

        # Validate ui.history_limit
        history_limit = self.get('ui.history_limit')
        if not isinstance(history_limit, int) or history_limit <= 0:
            errors.append(
                f"ui.history_limit must be positive integer, got {history_limit}"
            )

        # Validate overlay.auto_dismiss_ms
        auto_dismiss = self.get('overlay.auto_dismiss_ms')
        if not isinstance(auto_dismiss, int) or auto_dismiss < 0:
            errors.append(
                f"overlay.auto_dismiss_ms must be non-negative integer, got {auto_dismiss}"
            )

        # Validate whisper.beam_size
        beam_size = self.get('whisper.beam_size')
        if not isinstance(beam_size, int) or beam_size < 1:
            errors.append(
                f"whisper.beam_size must be positive integer, got {beam_size}"
            )

        # Validate whisper.temperature
        temperature = self.get('whisper.temperature')
        if not isinstance(temperature, (int, float)) or temperature < 0:
            errors.append(
                f"whisper.temperature must be non-negative number, got {temperature}"
            )

        # Validate boolean values
        bool_keys = [
            'app.autostart',
            'app.minimize_to_tray',
            'app.show_notifications',
            'whisper.fp16',
            'audio.noise_reduction',
            'audio.vad_enabled',
            'overlay.enabled',
            'storage.save_audio_files'
        ]
        for key in bool_keys:
            value = self.get(key)
            if not isinstance(value, bool):
                errors.append(f"{key} must be boolean, got {type(value).__name__}")

        # Validate storage.retention_days
        retention = self.get('storage.retention_days')
        if not isinstance(retention, int) or retention < 0:
            errors.append(
                f"storage.retention_days must be non-negative integer, got {retention}"
            )

        # Validate overlay.monitor
        monitor = self.get('overlay.monitor')
        if not isinstance(monitor, int) or monitor < 0:
            errors.append(
                f"overlay.monitor must be non-negative integer, got {monitor}"
            )

        # Validate ui.font_size
        font_size = self.get('ui.font_size')
        if not isinstance(font_size, int) or font_size < 8 or font_size > 72:
            errors.append(
                f"ui.font_size must be integer between 8 and 72, got {font_size}"
            )

        return errors

    def reset_to_defaults(self) -> None:
        """
        Reset all settings to defaults.

        Does NOT save automatically - call save() if desired.
        """
        self.config = copy.deepcopy(self.DEFAULT_CONFIG)
        logger.info("Configuration reset to defaults")

    def get_all(self) -> Dict[str, Any]:
        """
        Get complete configuration dictionary.

        Returns:
            Copy of entire config (modifications won't affect config)
        """
        return copy.deepcopy(self.config)
