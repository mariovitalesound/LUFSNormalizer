"""
Configuration load/save/migrate for LUFS Normalizer.

Handles v2.x -> v3.x config migration automatically.
"""

import json
from pathlib import Path

from .core.presets import LUFS_PRESETS, DEFAULT_FAVORITES

DEFAULT_CONFIG = {
    'input_folder': '',
    'output_folder': '',
    'target_lufs': -24.0,
    'peak_ceiling': -2.0,
    'preset_name': 'broadcast_us',
    'favorite_presets': list(DEFAULT_FAVORITES),
    'strict_lufs_matching': True,
    'auto_open_output': True,
    'bit_depth': 'preserve',
    'sample_rate': 'preserve',
    'use_batch_folders': True,
    'generate_log': True,
    'generate_csv': True,
    # v3.0 new fields
    'embed_bwf': False,
    'parallel_processing': False,
    'parallel_workers': 0,  # 0 = auto (CPU count)
    'watch_input_folder': '',
    'watch_output_folder': '',
    'config_version': 3,
}


def load_config(config_path):
    """
    Load config from JSON file with v2 -> v3 migration.

    Returns a config dict with all required fields populated.
    """
    config = dict(DEFAULT_CONFIG)
    config_file = Path(config_path)

    # Try user config first, then bundled default
    load_path = config_file
    if not load_path.exists():
        default_path = config_file.parent / 'config.default.json'
        if default_path.exists():
            load_path = default_path

    if load_path.exists():
        try:
            with open(load_path, 'r') as f:
                user_config = json.load(f)

            # v2 -> v3 migration
            if 'config_version' not in user_config:
                user_config = _migrate_v2_to_v3(user_config)

            config.update(user_config)
        except Exception:
            pass

    # Validate favorites
    valid_favorites = [p for p in config['favorite_presets'] if p in LUFS_PRESETS]
    if not valid_favorites:
        valid_favorites = list(DEFAULT_FAVORITES)
    config['favorite_presets'] = valid_favorites[:5]

    return config


def save_config(config, config_path):
    """Save config dict to JSON file."""
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Warning: Could not save config: {e}")


def _migrate_v2_to_v3(user_config):
    """Migrate v2.x config to v3.x format."""
    # Rename old preset keys
    old_to_new = {'broadcast': 'broadcast_eu', 'game': 'game_mobile'}
    if 'preset_name' in user_config:
        if user_config['preset_name'] in old_to_new:
            user_config['preset_name'] = old_to_new[user_config['preset_name']]

    # Add v3 defaults for new fields
    user_config.setdefault('embed_bwf', False)
    user_config.setdefault('parallel_processing', False)
    user_config.setdefault('parallel_workers', 0)
    user_config.setdefault('watch_input_folder', '')
    user_config.setdefault('watch_output_folder', '')
    user_config['config_version'] = 3

    return user_config
