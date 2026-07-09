"""
Tests for core.processor.process_single_file().

Covers every result type:
  - 'success' (normal & undershoot)
  - 'skipped' (silence)
  - 'needs_limiting' (strict mode rejects loud file)
  - 'blocked' (multichannel, upsample)
  - 'error' (file unreadable / corrupt)

Plus the Round 1 fixes:
  - #3: dither/clip ordering doesn't blow past PCM range
  - #4: reported final_lufs matches the file on disk
  - #5: >2 channels rejected
"""

import numpy as np
import pytest
import soundfile as sf
import pyloudnorm as pyln

from lufs_normalizer.core.processor import process_single_file
from lufs_normalizer.core.measurement import measure_true_peak


SR = 48000


@pytest.fixture
def out_dirs(tmp_path):
    n = tmp_path / 'normalized'
    nl = tmp_path / 'needs_limiting'
    n.mkdir()
    return str(n), str(nl)


def _measure_file_lufs(path):
    data, sr = sf.read(str(path))
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    return pyln.Meter(sr).integrated_loudness(data)


class TestSuccessPath:
    def test_normalizes_to_target_within_tolerance(self, make_wav, out_dirs):
        """Normalized output measures within ±0.1 LU of target."""
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2)
        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, rng_seed=1,
        )
        assert res['type'] == 'success'
        assert res['result']['status'] == 'OK'

        actual = _measure_file_lufs(res['output_file'])
        assert abs(actual - (-23.0)) < 0.1, f"file LUFS {actual} != -23 ±0.1"

    def test_reported_lufs_matches_disk_file(self, make_wav, out_dirs):
        """Round 1 fix #4: result['final_lufs'] equals an independent measurement."""
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2, subtype='PCM_24')
        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='16', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, rng_seed=1,
        )
        assert res['type'] == 'success'
        reported = res['result']['final_lufs']
        actual = _measure_file_lufs(res['output_file'])
        assert abs(reported - actual) < 0.05, (
            f"reported {reported} doesn't match disk {actual}"
        )

    def test_output_below_peak_ceiling(self, make_wav, out_dirs):
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2)
        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, rng_seed=1,
        )
        peak = res['result']['true_peak_dBTP']
        assert peak <= -1.0 + 0.1, f"peak {peak} exceeded ceiling"

    def test_no_clipping_after_dither(self, make_wav, out_dirs):
        """Round 1 fix #3: no samples beyond ±full-scale on disk after dither.

        PCM_16 max sample magnitude on read is < 1.0 (32767/32768) so a tiny
        margin is allowed for the LSB-of-dither boundary case.
        """
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2)
        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='16', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, rng_seed=1,
        )
        data, _ = sf.read(res['output_file'])
        assert np.max(np.abs(data)) <= 1.0

    def test_filename_lufs_suffix(self, make_wav, out_dirs):
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(name='source.wav', lufs=-18.0, channels=2)
        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['output_file'].endswith('source_-23LUFS.wav')

    def test_mono_input_handled(self, make_wav, out_dirs):
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=1)
        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['type'] == 'success'
        actual = _measure_file_lufs(res['output_file'])
        assert abs(actual - (-23.0)) < 0.1


class TestSilenceSkip:
    def test_silent_file_skipped(self, silent_wav, out_dirs):
        norm_dir, nl_dir = out_dirs
        res = process_single_file(
            str(silent_wav), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['type'] == 'skipped'
        assert res['error']['reason'] == 'too_quiet'


class TestStrictPeakMode:
    def test_peaky_file_diverted_to_needs_limiting(self, peaky_quiet_wav, out_dirs):
        """Strict mode: a quiet but peaky file targeted at a loud LUFS gets diverted.

        Peaky-quiet input (~-30 LUFS, near-FS spike) → target -9 LUFS requires
        ~+21 dB gain, which pushes the spike well above any sane peak ceiling.
        """
        norm_dir, nl_dir = out_dirs
        res = process_single_file(
            str(peaky_quiet_wav), target_lufs=-9.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['type'] == 'needs_limiting', f"got {res['type']}: {res}"
        assert res['skipped']['reason'] == 'would_exceed_peak_ceiling'
        assert 'needs_limiting' in res['output_file'].replace('\\', '/')


class TestDriftMode:
    def test_drift_undershoots_target_to_protect_peak(self, peaky_quiet_wav, out_dirs):
        """Drift mode: gain reduced to keep peak at ceiling, LUFS undershoots."""
        norm_dir, nl_dir = out_dirs
        res = process_single_file(
            str(peaky_quiet_wav), target_lufs=-9.0, peak_ceiling=-1.0,
            strict_lufs_matching=False, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['type'] == 'success'
        peak = res['result']['true_peak_dBTP']
        assert peak <= -1.0 + 0.5, f"drift mode peak {peak} exceeded ceiling"
        # And LUFS should undershoot the target (peak limited the gain)
        final_lufs = res['result']['final_lufs']
        assert final_lufs < -9.0 - 1.0, f"expected undershoot below -10, got {final_lufs}"


class TestMultichannelRejection:
    def test_six_channel_blocked(self, surround_wav, out_dirs):
        """Round 1 fix #5: 5.1 surround is rejected."""
        norm_dir, nl_dir = out_dirs
        res = process_single_file(
            str(surround_wav), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['type'] == 'blocked'
        assert res['error']['reason'] == 'multichannel_unsupported'


class TestSampleRateConversion:
    def test_upsample_blocked(self, make_wav, tmp_path, out_dirs):
        """Upsampling is intentionally refused — no signal there to recover."""
        norm_dir, nl_dir = out_dirs
        # Write a 44.1k file
        path = tmp_path / 'low_sr.wav'
        n = int(44100 * 4.0)
        t = np.arange(n) / 44100
        data = (0.1 * np.sin(2 * np.pi * 1000 * t))
        data = np.column_stack([data, data])
        sf.write(str(path), data, 44100, subtype='PCM_24')

        res = process_single_file(
            str(path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve',
            sample_rate='48000 Hz',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['type'] == 'blocked'
        assert res['error']['reason'] == 'upsample_blocked'

    def test_downsample_works(self, tmp_path, out_dirs):
        """48k → 44.1k succeeds and writes at the lower rate."""
        norm_dir, nl_dir = out_dirs
        path = tmp_path / 'hi_sr.wav'
        n = int(SR * 4.0)
        t = np.arange(n) / SR
        data = (0.1 * np.sin(2 * np.pi * 1000 * t))
        data = np.column_stack([data, data])
        sf.write(str(path), data, SR, subtype='PCM_24')

        res = process_single_file(
            str(path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve',
            sample_rate='44100 Hz',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['type'] == 'success'
        assert res['result']['sample_rate'] == 44100

    def test_downsample_scipy_fallback(self, tmp_path, out_dirs, monkeypatch):
        """When soxr is absent, scipy.signal.resample is used and succeeds."""
        import builtins
        real_import = builtins.__import__

        def _block_soxr(name, *args, **kwargs):
            if name == 'soxr':
                raise ImportError("soxr blocked for test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, '__import__', _block_soxr)

        norm_dir, nl_dir = out_dirs
        path = tmp_path / 'hi_sr.wav'
        n = int(SR * 4.0)
        t = np.arange(n) / SR
        data = 0.1 * np.sin(2 * np.pi * 1000 * t)
        data = np.column_stack([data, data])
        sf.write(str(path), data, SR, subtype='PCM_24')

        res = process_single_file(
            str(path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve',
            sample_rate='44100 Hz',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['type'] == 'success', f"expected success, got {res}"
        assert res['result']['sample_rate'] == 44100
        msgs = ' '.join(m for _, m in res['log_messages'])
        assert 'scipy' in msgs

    def test_downsample_blocked_when_neither_available(self, tmp_path, out_dirs, monkeypatch):
        """When both soxr and scipy are absent, returns blocked with reason src_missing_dependency."""
        import builtins
        real_import = builtins.__import__

        def _block_both(name, *args, **kwargs):
            if name in ('soxr', 'scipy'):
                raise ImportError(f"{name} blocked for test")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, '__import__', _block_both)

        norm_dir, nl_dir = out_dirs
        path = tmp_path / 'hi_sr.wav'
        n = int(SR * 4.0)
        t = np.arange(n) / SR
        data = 0.1 * np.sin(2 * np.pi * 1000 * t)
        data = np.column_stack([data, data])
        sf.write(str(path), data, SR, subtype='PCM_24')

        res = process_single_file(
            str(path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve',
            sample_rate='44100 Hz',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['type'] == 'blocked'
        assert res['error']['reason'] == 'src_missing_dependency'

    def test_post_src_peak_reclassifies_strict(self, make_wav, out_dirs, monkeypatch):
        """Strict: file passes the pre-SRC ceiling check but its measured peak
        exceeds the ceiling AFTER downsampling → moved to needs_limiting/ with
        reason 'exceeded_post_src', and removed from normalized/."""
        import lufs_normalizer.core.processor as proc

        # TP below ceiling at the original 48k rate (pre-SRC check passes),
        # above ceiling at the 44.1k target rate (post-SRC check must fire).
        def fake_tp(data, sr):
            return -0.3 if sr == 44100 else -2.0
        monkeypatch.setattr(proc, 'measure_true_peak', fake_tp)

        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2, sample_rate=48000, subtype='PCM_24')

        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve',
            sample_rate='44100 Hz',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, rng_seed=1,
        )

        assert res['type'] == 'needs_limiting', f"got {res['type']}: {res}"
        assert res['skipped']['reason'] == 'exceeded_post_src'
        assert res['skipped']['predicted_peak_dBTP'] == -0.3

        from pathlib import Path
        out = Path(res['output_file'])
        assert 'needs_limiting' in str(out).replace('\\', '/')
        assert out.exists(), "file must be present in needs_limiting/"
        # Not left behind in normalized/
        assert list(Path(norm_dir).glob('*_-23LUFS.wav')) == [], \
            "output must be removed from normalized/ after relocation"

    def test_post_src_check_skipped_when_no_conversion(self, make_wav, out_dirs, monkeypatch):
        """No SRC (sample_rate='preserve') → the new post-SRC reclassification
        branch never fires; the existing pre-SRC check owns the decision, so the
        reason stays 'would_exceed_peak_ceiling' (not 'exceeded_post_src')."""
        import lufs_normalizer.core.processor as proc
        monkeypatch.setattr(proc, 'measure_true_peak', lambda data, sr: -0.3)

        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2, subtype='PCM_24')
        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, rng_seed=1,
        )
        assert res['type'] == 'needs_limiting'
        assert res['skipped']['reason'] == 'would_exceed_peak_ceiling'

    def test_post_dither_peak_reclassifies_strict(self, make_wav, out_dirs, monkeypatch):
        """Strict, no SRC: file passes the pre-SRC ceiling check but its measured
        peak exceeds the ceiling AFTER bit-depth dither/quantization → moved to
        needs_limiting/ with reason 'exceeded_post_dither', removed from normalized/."""
        import lufs_normalizer.core.processor as proc

        # No SRC (sample_rate='preserve') means both true-peak calls use the same
        # rate, so key on call order instead: 1st call = pre-SRC prediction (below
        # ceiling → file written), 2nd call = final measurement (above ceiling).
        calls = {'n': 0}
        def fake_tp(data, sr):
            calls['n'] += 1
            return -2.0 if calls['n'] == 1 else -0.3
        monkeypatch.setattr(proc, 'measure_true_peak', fake_tp)

        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2, subtype='PCM_24')

        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='16', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, rng_seed=1,
        )

        assert res['type'] == 'needs_limiting', f"got {res['type']}: {res}"
        assert res['skipped']['reason'] == 'exceeded_post_dither'
        assert res['skipped']['predicted_peak_dBTP'] == -0.3

        from pathlib import Path
        out = Path(res['output_file'])
        assert 'needs_limiting' in str(out).replace('\\', '/')
        assert out.exists(), "file must be present in needs_limiting/"
        # Not left behind in normalized/
        assert list(Path(norm_dir).glob('*_-23LUFS.wav')) == [], \
            "output must be removed from normalized/ after relocation"


class TestBitDepth:
    def test_explicit_16_writes_16(self, make_wav, out_dirs):
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2, subtype='PCM_24')
        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='16', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['type'] == 'success'
        info = sf.info(res['output_file'])
        assert info.subtype == 'PCM_16'
        assert res['result']['bit_depth'] == 16

    def test_preserve_keeps_24(self, make_wav, out_dirs):
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2, subtype='PCM_24')
        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        info = sf.info(res['output_file'])
        assert info.subtype == 'PCM_24'


class TestDryRun:
    def test_dry_run_returns_dry_run_type(self, make_wav, out_dirs):
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2)
        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, dry_run=True,
        )
        assert res['type'] == 'dry_run'

    def test_dry_run_writes_no_file(self, make_wav, out_dirs, tmp_path):
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2)
        process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, dry_run=True,
        )
        assert list(tmp_path.rglob('*_-23LUFS.wav')) == [], "dry run must not write output"

    def test_dry_run_result_fields(self, make_wav, out_dirs):
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2)
        res = process_single_file(
            str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, dry_run=True,
        )
        r = res['result']
        assert r['predicted_status'] == 'OK'
        assert abs(r['original_lufs'] - (-18.0)) < 0.2
        assert abs(r['gain_needed_db'] - (-5.0)) < 0.2
        assert r['target_lufs'] == -23.0

    def test_dry_run_strict_predicts_needs_limiting(self, peaky_quiet_wav, out_dirs):
        """Peaky-quiet file at loud target → NEEDS_LIMITING in dry-run strict mode."""
        norm_dir, nl_dir = out_dirs
        res = process_single_file(
            str(peaky_quiet_wav), target_lufs=-9.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, dry_run=True,
        )
        assert res['type'] == 'dry_run'
        assert res['result']['predicted_status'] == 'NEEDS_LIMITING'
        assert res['output_file'] is None

    def test_dry_run_drift_predicts_undershoot(self, peaky_quiet_wav, out_dirs):
        """Drift mode dry-run shows OK_UNDERSHOOT when peak would exceed ceiling."""
        norm_dir, nl_dir = out_dirs
        res = process_single_file(
            str(peaky_quiet_wav), target_lufs=-9.0, peak_ceiling=-1.0,
            strict_lufs_matching=False, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir, dry_run=True,
        )
        assert res['type'] == 'dry_run'
        assert res['result']['predicted_status'] == 'OK_UNDERSHOOT'


class TestErrorHandling:
    def test_unreadable_file_returns_error(self, tmp_path, out_dirs):
        """Corrupt input file produces an 'error' result, not an exception."""
        norm_dir, nl_dir = out_dirs
        bad = tmp_path / 'bad.wav'
        bad.write_bytes(b'NOT A REAL WAV FILE')
        res = process_single_file(
            str(bad), target_lufs=-23.0, peak_ceiling=-1.0,
            strict_lufs_matching=True, bit_depth='preserve', sample_rate='preserve',
            normalized_path=norm_dir, needs_limiting_path=nl_dir,
        )
        assert res['type'] == 'error'
        assert 'error' in res['error']


class TestDeterminism:
    def test_same_seed_produces_byte_identical_output(self, make_wav, out_dirs):
        """Given the same rng_seed, two runs produce byte-identical output files."""
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2)

        # Run twice with same seed, into separate dirs to avoid collision
        out1 = str(tmp_dir1 := __import__('pathlib').Path(norm_dir) / 'a')
        out2 = str(tmp_dir2 := __import__('pathlib').Path(norm_dir) / 'b')
        tmp_dir1.mkdir()
        tmp_dir2.mkdir()

        for out, seed in [(out1, 7), (out2, 7)]:
            process_single_file(
                str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
                strict_lufs_matching=True, bit_depth='16', sample_rate='preserve',
                normalized_path=out, needs_limiting_path=nl_dir, rng_seed=seed,
            )

        a = (tmp_dir1).glob('*.wav').__next__()
        b = (tmp_dir2).glob('*.wav').__next__()
        assert a.read_bytes() == b.read_bytes()

    def test_different_seeds_produce_different_dither(self, make_wav, out_dirs):
        norm_dir, nl_dir = out_dirs
        in_path = make_wav(lufs=-18.0, channels=2)

        from pathlib import Path
        d1 = Path(norm_dir) / 's1'; d1.mkdir()
        d2 = Path(norm_dir) / 's2'; d2.mkdir()

        for out, seed in [(str(d1), 1), (str(d2), 2)]:
            process_single_file(
                str(in_path), target_lufs=-23.0, peak_ceiling=-1.0,
                strict_lufs_matching=True, bit_depth='16', sample_rate='preserve',
                normalized_path=out, needs_limiting_path=nl_dir, rng_seed=seed,
            )

        a = next(d1.glob('*.wav'))
        b = next(d2.glob('*.wav'))
        # Different dither realizations → different byte content
        assert a.read_bytes() != b.read_bytes()
