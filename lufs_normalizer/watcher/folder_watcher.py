"""
Watchdog-based folder monitoring for auto-processing audio files.

Monitors a directory for new .wav/.aiff files, waits for write completion,
then queues them for LUFS normalization.
"""

import time
import logging
import threading
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

from ..core.processor import process_single_file


AUDIO_EXTENSIONS = {'.wav', '.aiff', '.aif'}


class _AudioFileHandler(FileSystemEventHandler):
    """Handle new audio file events."""

    def __init__(self, watcher):
        super().__init__()
        self.watcher = watcher

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in AUDIO_EXTENSIONS:
            self.watcher._queue_file(path)


class FolderWatcher:
    """
    Watch a folder for new audio files and auto-process them.

    Args:
        watch_dir: Directory to monitor
        output_dir: Directory for processed output
        settings: Dict with processing settings (target_lufs, peak_ceiling, etc.)
        callback: Optional function called after each file: callback(filename, status, details)
    """

    def __init__(self, watch_dir, output_dir, settings, callback=None):
        if not HAS_WATCHDOG:
            raise ImportError("watchdog package required: pip install watchdog>=3.0.0")

        self.watch_dir = Path(watch_dir)
        self.output_dir = Path(output_dir)
        self.settings = settings
        self.callback = callback
        self._observer = None
        self._running = False
        self._process_thread = None
        self._queue = []
        self._queue_lock = threading.Lock()

    def start(self):
        """Start watching the folder."""
        if self._running:
            return

        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._running = True
        handler = _AudioFileHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.watch_dir), recursive=False)
        self._observer.start()

        self._process_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._process_thread.start()

        logging.info(f"Watch started: {self.watch_dir}")

    def stop(self):
        """Stop watching."""
        self._running = False
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        logging.info("Watch stopped")

    def is_running(self):
        return self._running

    def _queue_file(self, path):
        """Add a file to the processing queue."""
        with self._queue_lock:
            if str(path) not in [str(p) for p in self._queue]:
                self._queue.append(path)
                logging.info(f"Queued: {path.name}")

    def _wait_for_write_completion(self, path, timeout=30, poll_interval=0.5):
        """Wait until file size stabilizes (write complete)."""
        prev_size = -1
        stable_count = 0
        elapsed = 0

        while elapsed < timeout:
            try:
                current_size = path.stat().st_size
                if current_size == prev_size and current_size > 0:
                    stable_count += 1
                    if stable_count >= 3:
                        return True
                else:
                    stable_count = 0
                prev_size = current_size
            except OSError:
                return False

            time.sleep(poll_interval)
            elapsed += poll_interval

        return False

    def _process_loop(self):
        """Background loop that processes queued files."""
        while self._running:
            path = None
            with self._queue_lock:
                if self._queue:
                    path = self._queue.pop(0)

            if path is None:
                time.sleep(0.5)
                continue

            # Wait for file to finish writing
            if not self._wait_for_write_completion(path):
                logging.warning(f"Skipped (write timeout): {path.name}")
                continue

            logging.info(f"Processing: {path.name}")

            try:
                result = process_single_file(
                    audio_path=str(path),
                    target_lufs=self.settings.get('target_lufs', -23.0),
                    peak_ceiling=self.settings.get('peak_ceiling', -1.0),
                    strict_lufs_matching=self.settings.get('strict_lufs_matching', True),
                    bit_depth=self.settings.get('bit_depth', 'preserve'),
                    sample_rate=self.settings.get('sample_rate', 'preserve'),
                    normalized_path=str(self.output_dir),
                    needs_limiting_path=str(self.output_dir / 'needs_limiting'),
                    embed_bwf=self.settings.get('embed_bwf', False),
                )

                status = result['type']
                filename = result['filename']

                if status == 'success':
                    logging.info(f"Done: {filename}")
                elif status == 'needs_limiting':
                    logging.warning(f"Needs limiting: {filename}")
                else:
                    logging.error(f"Failed: {filename}")

                if self.callback:
                    self.callback(filename, status, result)

            except Exception as e:
                logging.error(f"Watch processing error for {path.name}: {e}")
                if self.callback:
                    self.callback(path.name, 'error', {'error': str(e)})
