#!/usr/bin/env python3
"""
LUFS Normalizer Core Engine — Backward Compatibility Shim

This file re-exports everything from lufs_normalizer.core so that
existing scripts using `from normalize_lufs_core import ...` continue to work.

For new code, use: from lufs_normalizer.core import ...
"""

# Re-export everything from the new package structure
from lufs_normalizer import VERSION, get_output_filename
from lufs_normalizer.core.presets import (
    LUFS_PRESETS, DEFAULT_FAVORITES,
    apply_lufs_preset, get_preset_for_lufs, get_preset_info
)
from lufs_normalizer.core.measurement import measure_true_peak, measure_lra
from lufs_normalizer.core.dither import apply_tpdf_dither
from lufs_normalizer.core.engine import LUFSNormalizer
from lufs_normalizer.core.processor import process_single_file

# CLI interface
if __name__ == '__main__':
    from lufs_normalizer.cli import main
    main()
