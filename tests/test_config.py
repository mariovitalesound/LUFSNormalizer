"""
Tests for config load/save/migrate and preset lookups.
"""

import json
import pytest

from lufs_normalizer.config import load_config, save_config, DEFAULT_CONFIG
from lufs_normalizer.core.presets import (
    LUFS_PRESETS, DEFAULT_FAVORITES,
    apply_lufs_preset, get_preset_for_lufs, get_preset_info,
)


class TestLoadConfig:
    def test_missing_file_returns_defaults(self, tmp_path):
        cfg = load_config(tmp_path / 'nonexistent.json')
        assert cfg['target_lufs'] == DEFAULT_CONFIG['target_lufs']
        assert cfg['config_version'] == 3

    def test_loads_user_overrides(self, tmp_path):
        path = tmp_path / 'config.json'
        path.write_text(json.dumps({
            'target_lufs': -16.0,
            'peak_ceiling': -1.0,
            'config_version': 3,
        }))
        cfg = load_config(path)
        assert cfg['target_lufs'] == -16.0
        assert cfg['peak_ceiling'] == -1.0

    def test_v2_config_migrated_to_v3(self, tmp_path):
        """Old config without config_version key is upgraded."""
        path = tmp_path / 'config.json'
        path.write_text(json.dumps({
            'target_lufs': -23.0,
            'preset_name': 'broadcast',
            # No config_version → triggers v2 migration
        }))
        cfg = load_config(path)
        assert cfg['config_version'] == 3
        assert cfg['preset_name'] == 'broadcast_eu'
        assert 'embed_bwf' in cfg
        assert 'parallel_processing' in cfg

    def test_v2_old_game_preset_renamed(self, tmp_path):
        path = tmp_path / 'config.json'
        path.write_text(json.dumps({'preset_name': 'game'}))
        cfg = load_config(path)
        assert cfg['preset_name'] == 'game_mobile'

    def test_invalid_favorites_replaced_with_defaults(self, tmp_path):
        path = tmp_path / 'config.json'
        path.write_text(json.dumps({
            'favorite_presets': ['nonexistent_preset', 'also_fake'],
            'config_version': 3,
        }))
        cfg = load_config(path)
        assert cfg['favorite_presets'] == list(DEFAULT_FAVORITES)

    def test_favorites_capped_at_five(self, tmp_path):
        path = tmp_path / 'config.json'
        path.write_text(json.dumps({
            'favorite_presets': list(LUFS_PRESETS.keys()),  # all of them
            'config_version': 3,
        }))
        cfg = load_config(path)
        assert len(cfg['favorite_presets']) == 5

    def test_corrupt_json_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / 'config.json'
        path.write_text('{this is not valid json')
        cfg = load_config(path)
        # Should not crash, should return defaults
        assert cfg['target_lufs'] == DEFAULT_CONFIG['target_lufs']

    def test_falls_back_to_default_file_if_user_missing(self, tmp_path):
        """If config.json is absent but config.default.json exists, use that."""
        default = tmp_path / 'config.default.json'
        default.write_text(json.dumps({'target_lufs': -16.0, 'config_version': 3}))
        cfg = load_config(tmp_path / 'config.json')
        assert cfg['target_lufs'] == -16.0


class TestSaveConfig:
    def test_round_trip(self, tmp_path):
        path = tmp_path / 'config.json'
        cfg = dict(DEFAULT_CONFIG)
        cfg['target_lufs'] = -18.0
        cfg['favorite_presets'] = ['broadcast_eu', 'streaming']
        save_config(cfg, path)

        loaded = load_config(path)
        assert loaded['target_lufs'] == -18.0
        assert loaded['favorite_presets'] == ['broadcast_eu', 'streaming']

    def test_save_to_unwritable_path_does_not_raise(self, tmp_path):
        """Save failures log a warning but don't crash the app."""
        # Path that doesn't exist as a directory
        bad = tmp_path / 'no_such_dir' / 'config.json'
        # Should not raise
        save_config(DEFAULT_CONFIG, bad)


class TestPresets:
    def test_all_presets_have_required_keys(self):
        for key, preset in LUFS_PRESETS.items():
            assert 'lufs' in preset, f"{key} missing 'lufs'"
            assert 'peak' in preset, f"{key} missing 'peak'"
            assert 'name' in preset
            assert 'description' in preset
            assert 'standard' in preset

    def test_apply_lufs_preset_known(self):
        lufs, peak = apply_lufs_preset('broadcast_eu')
        assert lufs == -23.0
        assert peak == -1.0

    def test_apply_lufs_preset_unknown_returns_default(self):
        lufs, peak = apply_lufs_preset('nonexistent')
        assert lufs == -23.0
        assert peak == -1.0

    def test_get_preset_for_lufs_exact_match(self):
        # broadcast_eu: -23, -1
        assert get_preset_for_lufs(-23.0, -1.0) == 'broadcast_eu'

    def test_get_preset_for_lufs_no_peak_match(self):
        # -23 LUFS with non-matching peak: returns first preset matching just LUFS
        match = get_preset_for_lufs(-23.0, -3.0)
        # Should return None because peak doesn't match any -23 preset
        # (broadcast_eu has peak -1.0, no other preset has -23 LUFS)
        assert match is None

    def test_get_preset_for_lufs_no_match(self):
        assert get_preset_for_lufs(-99.9, -1.0) is None

    def test_get_preset_for_lufs_invalid_input(self):
        assert get_preset_for_lufs('not a number', -1.0) is None

    def test_get_preset_info_known(self):
        info = get_preset_info('streaming')
        assert info is not None
        assert info['lufs'] == -14.0

    def test_get_preset_info_unknown(self):
        assert get_preset_info('nonexistent') is None

    def test_default_favorites_all_valid(self):
        for fav in DEFAULT_FAVORITES:
            assert fav in LUFS_PRESETS, f"DEFAULT_FAVORITES contains invalid '{fav}'"
