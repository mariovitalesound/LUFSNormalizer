"""
BWF BEXT and iXML metadata injection for WAV files.

Writes broadcast metadata directly into RIFF/WAV chunk structure
for game audio pipelines (Wwise, FMOD) and broadcast compliance.

Large chunks (e.g. 'data') are stream-copied rather than loaded
into memory, keeping RAM usage constant regardless of file size.
"""

import struct
import os
import tempfile
import shutil
import logging
from datetime import datetime

# Chunks whose payloads are small enough to always load into memory.
# Everything else (data, unknown large chunks) is stream-copied.
_SMALL_CHUNK_IDS = {b'fmt ', b'bext', b'iXML', b'fact', b'cue ', b'LIST', b'JUNK', b'PAD '}

_COPY_BUF_SIZE = 4 * 1024 * 1024  # 4 MB stream-copy buffer


def _read_riff_chunks(filepath):
    """
    Read chunk metadata from a RIFF WAV file.

    Small, known chunks (fmt, bext, iXML, etc.) are read into memory.
    Large chunks (data, etc.) store only their file offset and size,
    avoiding hundreds-of-MB RAM spikes on large broadcast files.

    Returns:
        source_path: the filepath (needed for stream-copy on write)
        chunks: list of tuples — either:
            (chunk_id, bytes)           for small in-memory chunks
            (chunk_id, (offset, size))  for large stream-referenced chunks
    """
    chunks = []
    with open(filepath, 'rb') as f:
        riff_header = f.read(4)
        if riff_header != b'RIFF':
            raise ValueError("Not a valid RIFF file")
        file_size = struct.unpack('<I', f.read(4))[0]
        wave_id = f.read(4)
        if wave_id != b'WAVE':
            raise ValueError("Not a valid WAVE file")

        pos = 12
        end = 8 + file_size
        while pos < end:
            f.seek(pos)
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                break
            chunk_size = struct.unpack('<I', f.read(4))[0]

            if chunk_id in _SMALL_CHUNK_IDS:
                chunk_data = f.read(chunk_size)
                chunks.append((chunk_id, chunk_data))
            else:
                # Store offset + size for stream-copy later
                data_offset = pos + 8
                chunks.append((chunk_id, (data_offset, chunk_size)))

            # Chunks are word-aligned (padded to even byte)
            pos += 8 + chunk_size
            if chunk_size % 2 != 0:
                pos += 1

    return filepath, chunks


def _write_riff_file(filepath, source_path, chunks):
    """
    Write chunks back into a RIFF WAV file.

    In-memory chunks (bytes) are written directly.
    Stream-referenced chunks (offset, size) are copied from source_path
    in buffered 4 MB reads to avoid RAM spikes.
    """
    with open(source_path, 'rb') as src, open(filepath, 'wb') as dst:
        # Placeholder for RIFF header
        dst.write(b'RIFF')
        dst.write(b'\x00\x00\x00\x00')  # Will be filled in
        dst.write(b'WAVE')

        for chunk_id, chunk_payload in chunks:
            if isinstance(chunk_payload, bytes):
                # In-memory chunk
                dst.write(chunk_id)
                dst.write(struct.pack('<I', len(chunk_payload)))
                dst.write(chunk_payload)
                # Pad to even byte
                if len(chunk_payload) % 2 != 0:
                    dst.write(b'\x00')
            else:
                # Stream-referenced chunk: (offset, size)
                offset, size = chunk_payload
                dst.write(chunk_id)
                dst.write(struct.pack('<I', size))
                # Buffered copy from source file
                src.seek(offset)
                remaining = size
                while remaining > 0:
                    read_size = min(_COPY_BUF_SIZE, remaining)
                    buf = src.read(read_size)
                    if not buf:
                        break
                    dst.write(buf)
                    remaining -= len(buf)
                # Pad to even byte
                if size % 2 != 0:
                    dst.write(b'\x00')

        # Go back and write the correct file size
        file_size = dst.tell() - 8
        dst.seek(4)
        dst.write(struct.pack('<I', file_size))


def _write_riff_inplace(wav_path, source_path, chunks):
    """Write to a temp file then replace the original — safe for in-place edits."""
    dir_name = os.path.dirname(wav_path) or '.'
    fd, tmp_path = tempfile.mkstemp(suffix='.wav', dir=dir_name)
    os.close(fd)
    try:
        _write_riff_file(tmp_path, source_path, chunks)
        shutil.move(tmp_path, wav_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _build_bext_chunk(description="", originator="", originator_ref="",
                      date="", time="", loudness_value=None,
                      loudness_range=None, max_true_peak=None):
    """
    Build a BEXT (Broadcast Extension) chunk per EBU Tech 3285.

    Fixed-size fields followed by optional coding history.
    """
    # Fixed fields
    desc_bytes = description.encode('ascii', errors='replace')[:256].ljust(256, b'\x00')
    orig_bytes = originator.encode('ascii', errors='replace')[:32].ljust(32, b'\x00')
    orig_ref_bytes = originator_ref.encode('ascii', errors='replace')[:32].ljust(32, b'\x00')
    date_bytes = date.encode('ascii', errors='replace')[:10].ljust(10, b'\x00')
    time_bytes = time.encode('ascii', errors='replace')[:8].ljust(8, b'\x00')

    # Time reference (64-bit sample count, set to 0)
    time_ref_low = struct.pack('<I', 0)
    time_ref_high = struct.pack('<I', 0)

    # Version (BEXT version 2 for loudness fields)
    version = struct.pack('<H', 2)

    # UMID (64 bytes, zeroed)
    umid = b'\x00' * 64

    # Loudness fields (int16, value * 100)
    lv = struct.pack('<h', int(loudness_value * 100)) if loudness_value is not None else struct.pack('<h', 0)
    lr = struct.pack('<h', int(loudness_range * 100)) if loudness_range is not None else struct.pack('<h', 0)
    mtp = struct.pack('<h', int(max_true_peak * 100)) if max_true_peak is not None else struct.pack('<h', 0)

    # MaxMomentaryLoudness and MaxShortTermLoudness (not measured, set to 0)
    mml = struct.pack('<h', 0)
    mstl = struct.pack('<h', 0)

    # Reserved (180 bytes)
    reserved = b'\x00' * 180

    bext_data = (desc_bytes + orig_bytes + orig_ref_bytes +
                 date_bytes + time_bytes + time_ref_low + time_ref_high +
                 version + umid + lv + lr + mtp + mml + mstl + reserved)

    return bext_data


def inject_bext_chunk(wav_path, metadata_dict):
    """
    Write BEXT chunk into an existing WAV file.

    Args:
        wav_path: Path to WAV file
        metadata_dict: Dict with keys:
            - description (str): Up to 256 chars
            - originator (str): Up to 32 chars
            - originator_reference (str): Up to 32 chars
            - origination_date (str): yyyy-mm-dd
            - origination_time (str): hh:mm:ss
            - loudness_value (float): LUFS value
            - loudness_range (float): LRA in LU
            - max_true_peak (float): dBTP value
    """
    try:
        source_path, chunks = _read_riff_chunks(wav_path)

        # Remove existing bext chunk if present
        chunks = [(cid, cdata) for cid, cdata in chunks if cid != b'bext']

        now = datetime.now()
        bext_data = _build_bext_chunk(
            description=metadata_dict.get('description', ''),
            originator=metadata_dict.get('originator', 'LUFS Normalizer'),
            originator_ref=metadata_dict.get('originator_reference', ''),
            date=metadata_dict.get('origination_date', now.strftime('%Y-%m-%d')),
            time=metadata_dict.get('origination_time', now.strftime('%H:%M:%S')),
            loudness_value=metadata_dict.get('loudness_value'),
            loudness_range=metadata_dict.get('loudness_range'),
            max_true_peak=metadata_dict.get('max_true_peak'),
        )

        # Insert bext right after fmt chunk (before data)
        new_chunks = []
        bext_inserted = False
        for cid, cdata in chunks:
            new_chunks.append((cid, cdata))
            if cid == b'fmt ' and not bext_inserted:
                new_chunks.append((b'bext', bext_data))
                bext_inserted = True

        if not bext_inserted:
            # fmt not found — insert before data
            new_chunks.insert(0, (b'bext', bext_data))

        _write_riff_inplace(wav_path, source_path, new_chunks)
        return True

    except Exception as e:
        logging.error(f"Failed to inject BEXT chunk into {wav_path}: {e}")
        return False


def inject_ixml_chunk(wav_path, xml_string):
    """
    Write iXML chunk into an existing WAV file.

    Used by Wwise/FMOD for extended metadata.

    Args:
        wav_path: Path to WAV file
        xml_string: iXML content as string
    """
    try:
        source_path, chunks = _read_riff_chunks(wav_path)

        # Remove existing iXML chunk
        chunks = [(cid, cdata) for cid, cdata in chunks if cid != b'iXML']

        ixml_data = xml_string.encode('utf-8')

        # Insert after bext if present, else after fmt
        new_chunks = []
        inserted = False
        for cid, cdata in chunks:
            new_chunks.append((cid, cdata))
            if cid == b'bext' and not inserted:
                new_chunks.append((b'iXML', ixml_data))
                inserted = True

        if not inserted:
            for i, (cid, cdata) in enumerate(new_chunks):
                if cid == b'fmt ':
                    new_chunks.insert(i + 1, (b'iXML', ixml_data))
                    inserted = True
                    break

        if not inserted:
            new_chunks.append((b'iXML', ixml_data))

        _write_riff_inplace(wav_path, source_path, new_chunks)
        return True

    except Exception as e:
        logging.error(f"Failed to inject iXML chunk into {wav_path}: {e}")
        return False


def build_ixml_for_normalization(target_lufs, final_lufs, lra_lu, true_peak, version):
    """Build a minimal iXML string for normalization metadata."""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<BWFXML>
  <IXML_VERSION>1.52</IXML_VERSION>
  <PROJECT>LUFS Normalizer</PROJECT>
  <NOTE>Normalized to {target_lufs} LUFS by LUFS Normalizer v{version}</NOTE>
  <USER>
    <TARGET_LUFS>{target_lufs}</TARGET_LUFS>
    <FINAL_LUFS>{final_lufs}</FINAL_LUFS>
    <LRA_LU>{lra_lu if lra_lu is not None else 'N/A'}</LRA_LU>
    <TRUE_PEAK_DBTP>{true_peak}</TRUE_PEAK_DBTP>
  </USER>
</BWFXML>"""
    return xml
