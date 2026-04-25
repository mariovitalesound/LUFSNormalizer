"""
End-to-end batch tests for LUFSNormalizer.

Verifies the full pipeline: input dir → processed output dir, including
batch folder layout, CSV reports, and aggregate counters.
"""

import csv
import numpy as np
import pytest
import soundfile as sf

from lufs_normalizer.core.engine import LUFSNormalizer


SR = 48000


def _write_wav(path, lufs=-18.0, channels=2, duration=4.0):
    import pyloudnorm as pyln
    n = int(duration * SR)
    t = np.arange(n) / SR
    data = 0.1 * np.sin(2 * np.pi * 1000 * t)
    if channels == 2:
        data = np.column_stack([data, data])
    cur = pyln.Meter(SR).integrated_loudness(
        data if data.ndim > 1 else data.reshape(-1, 1)
    )
    if np.isfinite(cur):
        data = data * (10 ** ((lufs - cur) / 20))
    sf.write(str(path), data, SR, subtype='PCM_24')


@pytest.fixture
def input_batch(tmp_path):
    """Three audio files at varied loudness for a small batch test."""
    in_dir = tmp_path / 'in'
    in_dir.mkdir()
    _write_wav(in_dir / 'quiet.wav', lufs=-30.0)
    _write_wav(in_dir / 'medium.wav', lufs=-18.0)
    _write_wav(in_dir / 'low_target.wav', lufs=-23.0)
    # A non-audio file that should be ignored
    (in_dir / 'readme.txt').write_text('ignore me')
    return in_dir


class TestBatchSequential:
    def test_processes_all_audio_files(self, input_batch, tmp_path):
        normalizer = LUFSNormalizer()
        success, total, log_path, csv_path, out_path = normalizer.normalize_batch(
            input_dir=str(input_batch),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
            peak_ceiling=-1.0,
            strict_lufs_matching=True,
        )
        assert total == 3, f"expected 3 audio files (txt ignored), got {total}"
        assert success == 3

    def test_csv_report_generated(self, input_batch, tmp_path):
        normalizer = LUFSNormalizer()
        _, _, _, csv_path, _ = normalizer.normalize_batch(
            input_dir=str(input_batch),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
        )
        assert csv_path is not None
        with open(csv_path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 3
        for row in rows:
            assert row['status'] == 'OK'
            assert abs(float(row['final_lufs']) - (-23.0)) < 0.2
            assert float(row['true_peak_dBTP']) <= -1.0 + 0.1

    def test_log_file_generated(self, input_batch, tmp_path):
        normalizer = LUFSNormalizer()
        _, _, log_path, _, _ = normalizer.normalize_batch(
            input_dir=str(input_batch),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
        )
        assert log_path is not None
        text = open(log_path).read()
        assert 'BATCH COMPLETE' in text
        assert 'quiet.wav' in text

    def test_batch_folder_layout(self, input_batch, tmp_path):
        """With use_batch_folders=True, output goes into timestamped subdir."""
        normalizer = LUFSNormalizer()
        _, _, _, _, out_path = normalizer.normalize_batch(
            input_dir=str(input_batch),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
            use_batch_folders=True,
        )
        # out_path is the 'normalized/' subfolder of the batch folder
        from pathlib import Path
        normalized = Path(out_path)
        assert normalized.name == 'normalized'
        assert normalized.parent.name.startswith('batch_')
        assert (normalized.parent / 'logs').is_dir()

    def test_flat_layout(self, input_batch, tmp_path):
        normalizer = LUFSNormalizer()
        _, _, _, _, out_path = normalizer.normalize_batch(
            input_dir=str(input_batch),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
            use_batch_folders=False,
        )
        from pathlib import Path
        # Files go directly in out_dir
        assert Path(out_path) == tmp_path / 'out'
        wavs = list((tmp_path / 'out').glob('*_-23LUFS.wav'))
        assert len(wavs) == 3

    def test_empty_input_returns_zero(self, tmp_path):
        empty = tmp_path / 'empty'
        empty.mkdir()
        normalizer = LUFSNormalizer()
        success, total, *_ = normalizer.normalize_batch(
            input_dir=str(empty),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
        )
        assert success == 0
        assert total == 0


class TestBatchSilenceAndProblems:
    def test_silent_file_skipped_in_batch(self, tmp_path):
        in_dir = tmp_path / 'in'
        in_dir.mkdir()
        _write_wav(in_dir / 'good.wav', lufs=-18.0)
        # Silent file
        sf.write(str(in_dir / 'silent.wav'),
                 np.zeros((SR * 2, 2), dtype=np.float32),
                 SR, subtype='PCM_24')

        normalizer = LUFSNormalizer()
        success, total, *_ = normalizer.normalize_batch(
            input_dir=str(in_dir),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
        )
        assert total == 2
        assert success == 1
        assert len(normalizer.skipped_silent) == 1


class TestBatchParallel:
    def test_parallel_matches_sequential_results(self, input_batch, tmp_path):
        """Parallel mode produces the same per-file final LUFS as sequential."""
        seq = LUFSNormalizer()
        seq.normalize_batch(
            input_dir=str(input_batch),
            output_dir=str(tmp_path / 'seq'),
            target_lufs=-23.0,
        )

        par = LUFSNormalizer()
        par.normalize_batch_parallel(
            input_dir=str(input_batch),
            output_dir=str(tmp_path / 'par'),
            target_lufs=-23.0,
            max_workers=2,
        )

        # Map by filename so we can compare regardless of completion order
        seq_by_name = {r['filename']: r for r in seq.results}
        par_by_name = {r['filename']: r for r in par.results}
        assert set(seq_by_name) == set(par_by_name)
        for name in seq_by_name:
            # Same target → same final LUFS within dither tolerance
            assert abs(seq_by_name[name]['final_lufs']
                       - par_by_name[name]['final_lufs']) < 0.5


class TestProgressCallback:
    def test_progress_invoked_for_each_file(self, input_batch, tmp_path):
        progress_calls = []
        normalizer = LUFSNormalizer()
        normalizer.set_progress_callback(
            lambda i, n, name: progress_calls.append((i, n, name))
        )
        normalizer.normalize_batch(
            input_dir=str(input_batch),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
        )
        assert len(progress_calls) == 3
        # i counts up from 1
        assert progress_calls[0][0] == 1
        assert progress_calls[-1][0] == 3
        # n is total
        assert all(c[1] == 3 for c in progress_calls)


class TestDryRunBatch:
    def test_dry_run_writes_no_audio_files(self, input_batch, tmp_path):
        normalizer = LUFSNormalizer()
        normalizer.normalize_batch(
            input_dir=str(input_batch),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
            dry_run=True,
            use_batch_folders=False,
        )
        assert list((tmp_path / 'out').rglob('*.wav')) == [], \
            "dry run must not write any audio files"

    def test_dry_run_produces_csv_report(self, input_batch, tmp_path):
        normalizer = LUFSNormalizer()
        _, _, _, csv_path, _ = normalizer.normalize_batch(
            input_dir=str(input_batch),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
            dry_run=True,
            use_batch_folders=False,
        )
        assert csv_path is not None
        import csv as csv_mod
        with open(csv_path) as f:
            rows = list(csv_mod.DictReader(f))
        assert len(rows) == 3
        assert 'predicted_status' in rows[0]
        assert all(r['predicted_status'] == 'OK' for r in rows)

    def test_dry_run_accumulates_dry_run_results(self, input_batch, tmp_path):
        normalizer = LUFSNormalizer()
        normalizer.normalize_batch(
            input_dir=str(input_batch),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
            dry_run=True,
            use_batch_folders=False,
        )
        assert len(normalizer.dry_run_results) == 3
        assert len(normalizer.results) == 0  # no real normalizations


class TestRecursive:
    @pytest.fixture
    def nested_input(self, tmp_path):
        """Input tree: root + two subdirectories, 5 audio files total."""
        root = tmp_path / 'in'
        sfx = root / 'sfx'
        music = root / 'music' / 'ambient'
        for d in (root, sfx, music):
            d.mkdir(parents=True)
        _write_wav(root / 'root.wav', lufs=-18.0)
        _write_wav(sfx / 'boom.wav', lufs=-20.0)
        _write_wav(sfx / 'click.wav', lufs=-22.0)
        _write_wav(music / 'loop.wav', lufs=-16.0)
        _write_wav(music / 'pad.wav', lufs=-24.0)
        (root / 'notes.txt').write_text('ignored')
        return root

    def test_recursive_finds_all_files(self, nested_input, tmp_path):
        normalizer = LUFSNormalizer()
        success, total, *_ = normalizer.normalize_batch(
            input_dir=str(nested_input),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
            recursive=True,
            use_batch_folders=False,
        )
        assert total == 5, f"expected 5 files across subfolders, got {total}"
        assert success == 5

    def test_non_recursive_finds_only_root_files(self, nested_input, tmp_path):
        normalizer = LUFSNormalizer()
        success, total, *_ = normalizer.normalize_batch(
            input_dir=str(nested_input),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
            recursive=False,
            use_batch_folders=False,
        )
        assert total == 1, f"flat scan should find only root.wav, got {total}"

    def test_recursive_mirrors_folder_hierarchy(self, nested_input, tmp_path):
        """Output tree matches input tree: sfx/ and music/ambient/ are recreated."""
        from pathlib import Path
        normalizer = LUFSNormalizer()
        normalizer.normalize_batch(
            input_dir=str(nested_input),
            output_dir=str(tmp_path / 'out'),
            target_lufs=-23.0,
            recursive=True,
            use_batch_folders=False,
        )
        out = tmp_path / 'out'
        assert any(out.glob('*-23LUFS.wav')), "root file missing"
        assert any((out / 'sfx').glob('*-23LUFS.wav')), "sfx/ subdir missing"
        assert any((out / 'music' / 'ambient').glob('*-23LUFS.wav')), \
            "music/ambient/ subdir missing"

    def test_recursive_parallel_same_count(self, nested_input, tmp_path):
        """Parallel recursive mode finds the same files as sequential."""
        seq = LUFSNormalizer()
        _, total_seq, *_ = seq.normalize_batch(
            input_dir=str(nested_input),
            output_dir=str(tmp_path / 'seq'),
            target_lufs=-23.0,
            recursive=True,
            use_batch_folders=False,
        )
        par = LUFSNormalizer()
        _, total_par, *_ = par.normalize_batch_parallel(
            input_dir=str(nested_input),
            output_dir=str(tmp_path / 'par'),
            target_lufs=-23.0,
            recursive=True,
            use_batch_folders=False,
            max_workers=2,
        )
        assert total_seq == total_par == 5
