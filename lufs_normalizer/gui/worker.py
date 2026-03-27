"""
QThread worker for batch audio processing.

Replaces the daemon thread + root.after() pattern from CustomTkinter.
Emits signals for thread-safe GUI updates.
"""

from PySide6.QtCore import QThread, Signal

from ..core.engine import LUFSNormalizer


class BatchWorker(QThread):
    """
    Worker thread for batch LUFS normalization.

    Signals:
        progress(int, int, str) - (current, total, filename)
        file_result(str, str, str) - (filename, status, details)
        finished(int, int, str, str, str) - (success, total, log_path, csv_path, output_path)
        error(str) - error message
    """

    progress = Signal(int, int, str)
    file_result = Signal(str, str, str)
    finished = Signal(int, int, str, str, str)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.normalizer = LUFSNormalizer()
        self.normalizer.set_progress_callback(self._on_progress)
        self.normalizer.set_result_callback(self._on_result)

        # Processing parameters
        self.input_dir = ""
        self.output_dir = ""
        self.target_lufs = -23.0
        self.peak_ceiling = -1.0
        self.bit_depth = "preserve"
        self.sample_rate = "preserve"
        self.use_batch_folders = True
        self.generate_log = True
        self.generate_csv = True
        self.strict_lufs_matching = True
        self.embed_bwf = False
        self.parallel = False
        self.max_workers = None

    def _on_progress(self, current, total, filename):
        self.progress.emit(current, total, filename)

    def _on_result(self, filename, status, details):
        self.file_result.emit(filename, status, details)

    def request_stop(self):
        """Request graceful stop of processing."""
        self.normalizer.request_stop()

    def run(self):
        """Execute batch processing in this thread."""
        try:
            if self.parallel:
                success, total, log_path, csv_path, output_path = \
                    self.normalizer.normalize_batch_parallel(
                        input_dir=self.input_dir,
                        output_dir=self.output_dir,
                        target_lufs=self.target_lufs,
                        peak_ceiling=self.peak_ceiling,
                        bit_depth=self.bit_depth,
                        sample_rate=self.sample_rate,
                        use_batch_folders=self.use_batch_folders,
                        generate_log=self.generate_log,
                        generate_csv=self.generate_csv,
                        strict_lufs_matching=self.strict_lufs_matching,
                        embed_bwf=self.embed_bwf,
                        max_workers=self.max_workers,
                    )
            else:
                success, total, log_path, csv_path, output_path = \
                    self.normalizer.normalize_batch(
                        input_dir=self.input_dir,
                        output_dir=self.output_dir,
                        target_lufs=self.target_lufs,
                        peak_ceiling=self.peak_ceiling,
                        bit_depth=self.bit_depth,
                        sample_rate=self.sample_rate,
                        use_batch_folders=self.use_batch_folders,
                        generate_log=self.generate_log,
                        generate_csv=self.generate_csv,
                        strict_lufs_matching=self.strict_lufs_matching,
                        embed_bwf=self.embed_bwf,
                    )

            self.finished.emit(
                success, total,
                log_path or "", csv_path or "", output_path or ""
            )
        except Exception as e:
            self.error.emit(str(e))
