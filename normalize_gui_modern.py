#!/usr/bin/env python3
"""
LUFS Normalizer GUI — Backward Compatibility Shim

This file launches the new PySide6 GUI from lufs_normalizer.gui.app.

For new code, use: python -m lufs_normalizer.gui.app
"""

import multiprocessing
multiprocessing.freeze_support()

from lufs_normalizer.gui.app import main

if __name__ == '__main__':
    main()
