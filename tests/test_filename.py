"""
Tests for get_output_filename: smart LUFS suffix replacement.
"""

import pytest

from lufs_normalizer import get_output_filename


class TestSimpleAppend:
    def test_appends_lufs_suffix(self):
        assert get_output_filename('audio.wav', -23.0) == 'audio_-23LUFS.wav'

    def test_int_target_omits_decimal(self):
        assert get_output_filename('a.wav', -23.0) == 'a_-23LUFS.wav'

    def test_float_target_keeps_decimal(self):
        assert get_output_filename('a.wav', -22.5) == 'a_-22.5LUFS.wav'

    def test_preserves_extension(self):
        assert get_output_filename('a.aiff', -23.0) == 'a_-23LUFS.aiff'
        assert get_output_filename('a.AIF', -23.0) == 'a_-23LUFS.AIF'


class TestReplaceLUFSSuffix:
    def test_replaces_existing_lufs_suffix(self):
        assert get_output_filename('audio_-18LUFS.wav', -23.0) == 'audio_-23LUFS.wav'

    def test_replaces_decimal_lufs_suffix(self):
        assert get_output_filename('a_-22.5LUFS.wav', -23.0) == 'a_-23LUFS.wav'

    def test_replaces_case_insensitive(self):
        assert get_output_filename('a_-18lufs.wav', -23.0) == 'a_-23LUFS.wav'
        assert get_output_filename('a_-18LUFS.wav', -16.0) == 'a_-16LUFS.wav'


class TestReplaceNormalizedSuffix:
    def test_replaces_normalized_suffix(self):
        assert get_output_filename('audio_normalized.wav', -23.0) == 'audio_-23LUFS.wav'


class TestEdgeCases:
    def test_filename_with_lufs_in_middle_not_replaced(self):
        """Pattern is anchored at end of stem; mid-name 'LUFS' isn't touched."""
        assert get_output_filename('LUFS_test.wav', -23.0) == 'LUFS_test_-23LUFS.wav'

    def test_path_with_directory(self):
        # Function operates on the stem; directory part is stripped
        result = get_output_filename('subdir/audio.wav', -23.0)
        assert result == 'audio_-23LUFS.wav'

    def test_positive_target_lufs(self):
        """Unusual but legal: positive target."""
        assert get_output_filename('a.wav', 0.0) == 'a_0LUFS.wav'
