#!/usr/bin/env python3
"""
LUFS Verification Tool
Measures actual LUFS of audio files
"""
import soundfile as sf
import pyloudnorm as pyln
import sys
from pathlib import Path

def measure_lufs(audio_file):
    """Measure integrated LUFS of an audio file"""
    try:
        # Load audio
        data, rate = sf.read(audio_file)
        
        # Create meter
        meter = pyln.Meter(rate)
        
        # Measure integrated loudness
        loudness = meter.integrated_loudness(data)
        
        return loudness, rate
    except Exception as e:
        print(f"ERROR: {e}")
        return None, None

def main():
    if len(sys.argv) < 2:
        print("LUFS Verification Tool")
        print("=" * 50)
        print("\nUsage: python verify_lufs.py <audio_file.wav>")
        print("\nExample:")
        print("  python verify_lufs.py test_tone_-18dB_normalized.wav")
        print("\nOr drag and drop a WAV file onto this script.")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    
    if not Path(audio_file).exists():
        print(f"ERROR: File not found: {audio_file}")
        sys.exit(1)
    
    print("=" * 50)
    print("LUFS VERIFICATION TOOL")
    print("=" * 50)
    print(f"\nFile: {Path(audio_file).name}")
    print("Measuring...")
    
    loudness, rate = measure_lufs(audio_file)
    
    if loudness is not None:
        print("\n" + "=" * 50)
        print(f"INTEGRATED LOUDNESS: {loudness:.1f} LUFS")
        print("=" * 50)
        print(f"Sample Rate: {rate} Hz")
        
        # Interpretation
        print("\nInterpretation:")
        if -24 < loudness < -22:
            print("  ✓ Broadcast standard (-23 LUFS)")
        elif -19 < loudness < -17:
            print("  ✓ Game audio standard (-18 LUFS)")
        elif -15 < loudness < -13:
            print("  ✓ Streaming standard (-14 LUFS)")
        else:
            print(f"  Custom target: {loudness:.1f} LUFS")
        
        print("\n" + "=" * 50)
    else:
        print("\nFailed to measure LUFS.")
        sys.exit(1)

if __name__ == "__main__":
    main()
