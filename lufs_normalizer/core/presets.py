"""
LUFS preset definitions for common broadcast, streaming, and game audio standards.
"""

LUFS_PRESETS = {
    # Primary/Common
    'broadcast_us': {
        'lufs': -24.0,
        'peak': -2.0,
        'name': 'Broadcast (US)',
        'description': 'ATSC A/85 — US Television',
        'standard': 'ATSC A/85'
    },
    'broadcast_eu': {
        'lufs': -23.0,
        'peak': -1.0,
        'name': 'Broadcast (EU)',
        'description': 'EBU R128 — European Television',
        'standard': 'EBU R128'
    },
    'streaming': {
        'lufs': -14.0,
        'peak': -1.0,
        'name': 'Streaming',
        'description': 'Spotify / YouTube / Amazon',
        'standard': 'Spotify/YouTube'
    },
    'podcast': {
        'lufs': -16.0,
        'peak': -1.0,
        'name': 'Podcast',
        'description': 'Apple Podcasts / Spoken Word',
        'standard': 'Apple Podcasts'
    },

    # Game Audio (ASWG)
    'game_console': {
        'lufs': -24.0,
        'peak': -1.0,
        'name': 'Game (Console)',
        'description': 'ASWG Home — Console/PC Games',
        'standard': 'ASWG-R001 Home'
    },
    'game_mobile': {
        'lufs': -18.0,
        'peak': -1.0,
        'name': 'Game (Mobile)',
        'description': 'ASWG Portable — Mobile Games',
        'standard': 'ASWG-R001 Portable'
    },

    # Film/Cinema
    'film': {
        'lufs': -24.0,
        'peak': -2.0,
        'name': 'Film / Cinema',
        'description': 'Theatrical Reference (not dialog-gated)',
        'standard': 'SMPTE RP 200'
    },

    # Music
    'music_dynamic': {
        'lufs': -14.0,
        'peak': -1.0,
        'name': 'Music (Dynamic)',
        'description': 'Balanced loudness with dynamics',
        'standard': 'Streaming optimized'
    },
    'music_loud': {
        'lufs': -9.0,
        'peak': -1.0,
        'name': 'Music (Loud)',
        'description': 'Modern competitive loudness',
        'standard': 'Contemporary pop/EDM'
    },

    # Reference
    'reference_cinema': {
        'lufs': -27.0,
        'peak': -2.0,
        'name': 'Cinema Dialog Ref',
        'description': 'Netflix-style dialog reference',
        'standard': 'Netflix 5.1'
    }
}

DEFAULT_FAVORITES = ['broadcast_us', 'streaming', 'podcast']


def apply_lufs_preset(preset_name):
    """Return LUFS and peak values for a preset."""
    if preset_name in LUFS_PRESETS:
        return LUFS_PRESETS[preset_name]['lufs'], LUFS_PRESETS[preset_name]['peak']
    return -23.0, -1.0


def get_preset_for_lufs(lufs_value, peak_value=None):
    """Return preset name if LUFS (and optionally peak) value matches a preset, else None."""
    try:
        lufs = float(lufs_value)
        peak = float(peak_value) if peak_value is not None else None

        for name, preset in LUFS_PRESETS.items():
            if abs(preset['lufs'] - lufs) < 0.01:
                if peak is not None:
                    if abs(preset['peak'] - peak) < 0.01:
                        return name
                else:
                    return name
    except (ValueError, TypeError):
        pass
    return None


def get_preset_info(preset_name):
    """Return full preset info dict, or None if not found."""
    return LUFS_PRESETS.get(preset_name, None)
