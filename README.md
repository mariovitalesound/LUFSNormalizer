# LUFS Normalizer

**Professional Broadcast-Grade Audio Normalization Tool**

Version 2.9.0 (GUI) | Engine v2.5.0

---

## Overview

LUFS Normalizer is a batch audio processing tool that normalizes audio files to industry-standard loudness levels (LUFS) while respecting True Peak limits. Designed for broadcast engineers, game audio professionals, podcast producers, and content creators who need consistent, compliant audio levels.

### Key Features

- **ITU-R BS.1770-4** integrated loudness measurement (pyloudnorm)
- **True Peak detection** (dBTP) with 4x oversampling - EBU R128 compliant
- **TPDF dithering** for professional bit depth reduction
- **SOXR VHQ resampling** (mastering-grade quality)
- **10 industry presets** covering broadcast, streaming, podcast, game, film, and music
- **Batch processing** with detailed CSV/log reports
- **Strict vs Drift mode** for flexible peak handling

---

## Peak Handling Modes

### Strict Mode (Default)

When enabled, files that would exceed the True Peak ceiling after normalization are **skipped entirely**. They are copied to a `needs_limiting/` subfolder for manual processing with a limiter in your DAW.

**Use case:** You need exact LUFS targets for broadcast compliance. No exceptions.

**Behavior:**
- File would exceed peak? → SKIP, copy to `needs_limiting/`
- All processed files are guaranteed to hit the exact target LUFS
- CSV report shows `reason: would_exceed_peak_ceiling` for skipped files

### Drift Mode

When Strict Mode is disabled, files that would exceed the peak ceiling have their **gain reduced** to protect the ceiling. The file is processed, but the final LUFS will undershoot the target.

**Use case:** You want all files processed, even if some end up quieter than the target.

**Behavior:**
- File would exceed peak? → Reduce gain to stay under ceiling
- Final LUFS may be quieter than target (e.g., -26 LUFS instead of -24 LUFS)
- CSV report shows `reason: peak_limited` for these files

---

## Presets

| Preset | LUFS | Peak | Standard |
|--------|------|------|----------|
| Broadcast (US) | -24 | -2.0 dBTP | ATSC A/85 |
| Broadcast (EU) | -23 | -1.0 dBTP | EBU R128 |
| Streaming | -14 | -1.0 dBTP | Spotify/YouTube |
| Podcast | -16 | -1.0 dBTP | Apple Podcasts |
| Game (Console) | -24 | -1.0 dBTP | ASWG-R001 Home |
| Game (Mobile) | -18 | -1.0 dBTP | ASWG-R001 Portable |
| Film / Cinema | -24 | -2.0 dBTP | SMPTE RP 200 |
| Music (Dynamic) | -14 | -1.0 dBTP | Streaming optimized |
| Music (Loud) | -9 | -1.0 dBTP | Contemporary pop/EDM |
| Cinema Dialog Ref | -27 | -2.0 dBTP | Netflix 5.1 |

---

## Preset Manager

The GUI includes a unified Preset Manager for selecting and organizing favorites.

### Features

- **Favorites Bar:** Up to 5 presets displayed on the main screen for quick access
- **Drag-and-Drop Reordering:** Grab the handle icon to reorder favorites with a smooth "lift and drop" animation
- **Live Validation:** Manually entering LUFS/Peak values that match a preset will automatically highlight that preset
- **Apply & Close:** Selecting a preset and clicking "Apply" applies it and closes the manager

### Lift-and-Drop System

The preset reordering uses a custom drag implementation:

1. **Ghost Clone:** When dragging, a semi-transparent clone follows your cursor
2. **Spacer Animation:** Other items shift to show the drop position ("parting the sea" effect)
3. **Safe Release:** Global button release handling ensures clean drag termination

---

## Installation

### Requirements

- Python 3.8+
- Windows / macOS / Linux

### Steps

1. Clone or download the repository:
   ```bash
   git clone https://github.com/yourusername/lufs-normalizer.git
   cd lufs-normalizer
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the GUI:
   ```bash
   python normalize_gui_modern.py
   ```

4. Or use the CLI:
   ```bash
   python normalize_lufs_core.py /path/to/input /path/to/output -t -24 -p -2
   ```

---

## CLI Usage

```bash
python normalize_lufs_core.py INPUT_DIR OUTPUT_DIR [OPTIONS]

Options:
  -t, --target FLOAT    Target LUFS (default: -23.0)
  -p, --peak FLOAT      Peak ceiling dBTP (default: -1.0)
  -b, --bits            Bit depth: preserve, 16, 24, 32 (default: preserve)
  -r, --rate            Sample rate: preserve, 44100, 48000 (default: preserve)
```

**Example:**
```bash
python normalize_lufs_core.py ./raw_audio ./normalized -t -16 -p -1 -b 24
```

---

## Output Structure

When "Organize output in timestamped batch folders" is enabled:

```
output_folder/
└── batch_20240115_143022_-24LUFS/
    ├── normalized/
    │   ├── audio1_-24LUFS.wav
    │   └── audio2_-24LUFS.wav
    ├── needs_limiting/
    │   └── hot_audio_-24LUFS.wav
    └── logs/
        ├── processing.log
        └── normalization_report.csv
```

---

## CSV Report Columns

| Column | Description |
|--------|-------------|
| filename | Original filename |
| status | OK, OK_UNDERSHOOT, SKIPPED, BLOCKED, FAILED |
| reason | ok, peak_limited, would_exceed_peak_ceiling, too_quiet, upsample_blocked |
| sample_rate | Output sample rate |
| bit_depth | Output bit depth |
| original_lufs | Measured input loudness |
| target_lufs | Requested target |
| final_lufs | Actual output loudness |
| gain_applied_db | Gain adjustment made |
| true_peak_dBTP | Final True Peak measurement |

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Up Arrow | Increase LUFS by 1.0 |
| Down Arrow | Decrease LUFS by 1.0 |
| Shift + Up | Increase LUFS by 0.1 |
| Shift + Down | Decrease LUFS by 0.1 |

---

## Building a Standalone Executable

See the PyInstaller command below to create a single-file Windows executable.

---

## Credits

Developed by Mario Vitale

**Libraries:**
- [pyloudnorm](https://github.com/csteinmetz1/pyloudnorm) - ITU-R BS.1770-4 loudness measurement
- [soundfile](https://github.com/bastibe/python-soundfile) - Audio file I/O
- [soxr](https://github.com/dofuuz/python-soxr) - High-quality resampling
- [customtkinter](https://github.com/TomSchimansky/CustomTkinter) - Modern dark-themed GUI

---

## License

MIT License
