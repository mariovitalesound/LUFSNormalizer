"""
Tests for the folder watcher.

Covers Round 1 fix #7 (startup scan) plus the live on_created path and
the write-completion stability check.
"""

import time
import pytest
import shutil

import numpy as np
import soundfile as sf

watchdog = pytest.importorskip('watchdog')
from lufs_normalizer.watcher.folder_watcher import FolderWatcher


SR = 48000


def _write_test_wav(path):
    """A minimal stereo WAV with measurable LUFS."""
    data = (0.05 * np.sin(2 * np.pi * 1000 * np.arange(SR * 4) / SR))
    stereo = np.column_stack([data, data])
    sf.write(str(path), stereo, SR, subtype='PCM_24')


def _wait_for(predicate, timeout=15.0, interval=0.1):
    """Poll `predicate` until True or timeout. Returns whether condition was met."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


class TestStartupScan:
    """Round 1 fix #7: pre-existing files in watch dir get queued on start()."""

    def test_existing_files_are_processed(self, tmp_path):
        watch = tmp_path / 'watch'
        out = tmp_path / 'out'
        watch.mkdir()

        # Drop two files BEFORE starting the watcher
        _write_test_wav(watch / 'a.wav')
        _write_test_wav(watch / 'b.wav')

        processed = []
        w = FolderWatcher(
            str(watch), str(out),
            settings={'target_lufs': -23.0, 'peak_ceiling': -1.0,
                      'strict_lufs_matching': False},
            callback=lambda name, status, r: processed.append((name, status)),
        )

        try:
            w.start()
            assert _wait_for(lambda: len(processed) >= 2)
        finally:
            w.stop()

        names = sorted(name for name, _ in processed)
        assert names == ['a.wav', 'b.wav']

    def test_non_audio_files_ignored_on_startup(self, tmp_path):
        """A .txt or .mp3 (unsupported) in the watch dir is not queued."""
        watch = tmp_path / 'watch'
        out = tmp_path / 'out'
        watch.mkdir()

        (watch / 'readme.txt').write_text('not audio')
        (watch / 'song.mp3').write_bytes(b'\x00' * 100)
        _write_test_wav(watch / 'real.wav')

        processed = []
        w = FolderWatcher(
            str(watch), str(out),
            settings={'target_lufs': -23.0, 'peak_ceiling': -1.0,
                      'strict_lufs_matching': False},
            callback=lambda name, status, r: processed.append(name),
        )

        try:
            w.start()
            _wait_for(lambda: 'real.wav' in processed)
            time.sleep(0.5)  # give other files a chance to (incorrectly) trigger
        finally:
            w.stop()

        assert processed == ['real.wav']


class TestLiveDetection:
    """Files dropped after the watcher starts are picked up."""

    def test_new_file_processed(self, tmp_path):
        watch = tmp_path / 'watch'
        out = tmp_path / 'out'
        watch.mkdir()

        processed = []
        w = FolderWatcher(
            str(watch), str(out),
            settings={'target_lufs': -23.0, 'peak_ceiling': -1.0,
                      'strict_lufs_matching': False},
            callback=lambda name, status, r: processed.append(name),
        )

        try:
            w.start()
            time.sleep(0.5)  # let observer settle
            # Atomic-ish drop: write to a temp name, move into place
            tmp_file = tmp_path / 'tmp.wav'
            _write_test_wav(tmp_file)
            shutil.move(str(tmp_file), str(watch / 'dropped.wav'))

            assert _wait_for(lambda: 'dropped.wav' in processed)
        finally:
            w.stop()


class TestWriteCompletion:
    """The watcher waits for file size to stabilize before processing."""

    def test_stable_file_passes(self, tmp_path):
        watch = tmp_path / 'watch'
        out = tmp_path / 'out'
        watch.mkdir()
        out.mkdir()

        # Pre-create a file so startup scan picks it up immediately
        _write_test_wav(watch / 'stable.wav')

        w = FolderWatcher(str(watch), str(out),
                          settings={'target_lufs': -23.0, 'peak_ceiling': -1.0,
                                    'strict_lufs_matching': False})
        # Direct check
        assert w._wait_for_write_completion(watch / 'stable.wav', timeout=5)

    def test_missing_file_times_out(self, tmp_path):
        watch = tmp_path / 'watch'
        watch.mkdir()
        w = FolderWatcher(str(watch), str(tmp_path / 'out'),
                          settings={'target_lufs': -23.0, 'peak_ceiling': -1.0})
        # Nonexistent file → returns False quickly
        assert not w._wait_for_write_completion(watch / 'no.wav', timeout=1)


class TestStartStop:
    def test_double_start_is_idempotent(self, tmp_path):
        """Calling start() twice doesn't crash or double-observe."""
        watch = tmp_path / 'watch'
        watch.mkdir()
        w = FolderWatcher(str(watch), str(tmp_path / 'out'),
                          settings={'target_lufs': -23.0, 'peak_ceiling': -1.0})
        try:
            w.start()
            w.start()  # should be a no-op
            assert w.is_running()
        finally:
            w.stop()

    def test_stop_when_not_running_is_safe(self, tmp_path):
        watch = tmp_path / 'watch'
        watch.mkdir()
        w = FolderWatcher(str(watch), str(tmp_path / 'out'),
                          settings={'target_lufs': -23.0, 'peak_ceiling': -1.0})
        # Should not raise
        w.stop()
