"""
LUFS Normalizer CLI entry point.

Usage:
    python -m lufs_normalizer input_dir output_dir [options]
    python -m lufs_normalizer --watch input_dir output_dir [options]
"""

import argparse
import sys
import os

from . import VERSION
from .core.engine import LUFSNormalizer


def main():
    parser = argparse.ArgumentParser(
        description=f'LUFS Normalizer v{VERSION} - Professional batch audio normalization',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  lufs_normalizer input/ output/ -t -23 -p -1
  lufs_normalizer input/ output/ --parallel --workers 8
  lufs_normalizer --watch input/ output/ -t -24 --bwf

Files that would exceed peak ceiling are SKIPPED and copied to a
'needs_limiting/' folder. Apply a limiter in your DAW, then re-process.
        """
    )
    parser.add_argument('input', help='Input directory')
    parser.add_argument('output', help='Output directory')
    parser.add_argument('-t', '--target', type=float, default=-23.0, help='Target LUFS (default: -23.0)')
    parser.add_argument('-p', '--peak', type=float, default=-1.0, help='Peak ceiling dBTP (default: -1.0)')
    parser.add_argument('-b', '--bits', choices=['preserve', '16', '24', '32'], default='preserve',
                        help='Output bit depth (default: preserve)')
    parser.add_argument('-r', '--rate', choices=['preserve', '44100', '48000'], default='preserve',
                        help='Output sample rate (default: preserve)')
    parser.add_argument('--no-batch-folders', action='store_true', help='Flat output (no timestamped folders)')
    parser.add_argument('--no-log', action='store_true', help='Skip log file generation')
    parser.add_argument('--no-csv', action='store_true', help='Skip CSV report generation')
    parser.add_argument('--drift', action='store_true', help='Drift mode: reduce gain to protect peak')
    parser.add_argument('--bwf', action='store_true', help='Embed BWF BEXT + iXML metadata in output WAV')

    # Parallel processing
    parser.add_argument('--parallel', action='store_true', help='Enable parallel processing')
    parser.add_argument('--workers', type=int, default=0,
                        help='Number of parallel workers (default: CPU count)')

    # Watch mode
    parser.add_argument('--watch', action='store_true',
                        help='Watch folder mode: auto-process new files')

    args = parser.parse_args()

    sr = 'preserve' if args.rate == 'preserve' else f'{args.rate} Hz'

    if args.watch:
        _run_watch_mode(args, sr)
    else:
        _run_batch_mode(args, sr)


def _run_batch_mode(args, sr):
    """Run standard batch processing."""
    normalizer = LUFSNormalizer()

    if args.parallel:
        workers = args.workers if args.workers > 0 else None
        print(f"Parallel mode: {workers or os.cpu_count()} workers")
        normalizer.normalize_batch_parallel(
            input_dir=args.input,
            output_dir=args.output,
            target_lufs=args.target,
            peak_ceiling=args.peak,
            bit_depth=args.bits,
            sample_rate=sr,
            use_batch_folders=not args.no_batch_folders,
            generate_log=not args.no_log,
            generate_csv=not args.no_csv,
            strict_lufs_matching=not args.drift,
            embed_bwf=args.bwf,
            max_workers=workers,
        )
    else:
        normalizer.normalize_batch(
            input_dir=args.input,
            output_dir=args.output,
            target_lufs=args.target,
            peak_ceiling=args.peak,
            bit_depth=args.bits,
            sample_rate=sr,
            use_batch_folders=not args.no_batch_folders,
            generate_log=not args.no_log,
            generate_csv=not args.no_csv,
            strict_lufs_matching=not args.drift,
            embed_bwf=args.bwf,
        )


def _run_watch_mode(args, sr):
    """Run watch folder mode."""
    try:
        from .watcher.folder_watcher import FolderWatcher
    except ImportError:
        print("Error: watchdog package required for watch mode.")
        print("Install with: pip install watchdog>=3.0.0")
        sys.exit(1)

    print(f"Watch mode: monitoring {args.input}")
    print(f"Output: {args.output}")
    print(f"Target: {args.target} LUFS | Peak: {args.peak} dBTP")
    print("Press Ctrl+C to stop.")

    settings = {
        'target_lufs': args.target,
        'peak_ceiling': args.peak,
        'bit_depth': args.bits,
        'sample_rate': sr,
        'strict_lufs_matching': not args.drift,
        'embed_bwf': args.bwf,
    }

    watcher = FolderWatcher(
        watch_dir=args.input,
        output_dir=args.output,
        settings=settings,
    )

    try:
        watcher.start()
        # Block until Ctrl+C
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping watch mode...")
        watcher.stop()
        print("Done.")


if __name__ == '__main__':
    main()
