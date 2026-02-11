#!/usr/bin/env python3
"""
Icon Generator for LUFS Normalizer
Generates .ico files for desktop and taskbar use.

Run once: python generate_icons.py
Outputs: app_icon.ico (desktop), taskbar_icon.ico (window)
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_lufs_meter_icon(size, include_text=False, bg_color="#1a1a2e", bar_colors=None):
    """
    Create a LUFS meter icon with vertical bars.

    Args:
        size: Icon size (width=height)
        include_text: Whether to include "LUFS" text at bottom
        bg_color: Background color
        bar_colors: List of colors for bars (gradient from green to yellow to red)
    """
    if bar_colors is None:
        bar_colors = ["#2ecc71", "#27ae60", "#f1c40f", "#e74c3c"]  # Green to red

    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw rounded rectangle background
    padding = max(1, size // 16)
    radius = max(2, size // 8)
    draw.rounded_rectangle(
        [padding, padding, size - padding, size - padding],
        radius=radius,
        fill=bg_color
    )

    # Calculate bar dimensions
    num_bars = 4
    bar_area_top = size // 6
    bar_area_bottom = size - size // 4 if include_text else size - size // 6
    bar_area_left = size // 5
    bar_area_right = size - size // 5

    bar_width = (bar_area_right - bar_area_left) // (num_bars * 2 - 1)
    bar_gap = bar_width
    max_bar_height = bar_area_bottom - bar_area_top

    # Bar heights (normalized levels - simulating a LUFS meter)
    bar_heights = [0.6, 0.85, 0.95, 0.5]  # Varying levels

    for i, (height_pct, color) in enumerate(zip(bar_heights, bar_colors)):
        x1 = bar_area_left + i * (bar_width + bar_gap)
        x2 = x1 + bar_width
        bar_height = int(max_bar_height * height_pct)
        y1 = bar_area_bottom - bar_height
        y2 = bar_area_bottom

        # Draw bar with slight rounded top
        bar_radius = max(1, bar_width // 4)
        draw.rounded_rectangle([x1, y1, x2, y2], radius=bar_radius, fill=color)

    # Add "LUFS" text for larger desktop icon
    if include_text and size >= 48:
        try:
            font_size = max(8, size // 8)
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()

        text = "LUFS"
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_x = (size - text_width) // 2
        text_y = size - size // 6 - (bbox[3] - bbox[1]) // 2
        draw.text((text_x, text_y), text, fill="#ffffff", font=font)

    return img


def create_simple_meter_icon(size, bg_color="#1a1a2e"):
    """
    Create a minimal meter icon for taskbar (no text, cleaner).
    """
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded background
    padding = max(1, size // 12)
    radius = max(2, size // 6)
    draw.rounded_rectangle(
        [padding, padding, size - padding, size - padding],
        radius=radius,
        fill=bg_color
    )

    # Simpler 3-bar design for small sizes
    num_bars = 3
    bar_area_top = size // 4
    bar_area_bottom = size - size // 4
    bar_area_left = size // 4
    bar_area_right = size - size // 4

    total_bar_width = bar_area_right - bar_area_left
    bar_width = total_bar_width // (num_bars * 2 - 1)
    bar_gap = bar_width
    max_bar_height = bar_area_bottom - bar_area_top

    # Heights and colors (blue theme to match app)
    bar_data = [
        (0.5, "#3498db"),   # Light blue
        (0.85, "#2d8f2d"),  # Green (peak)
        (0.65, "#3498db"),  # Light blue
    ]

    for i, (height_pct, color) in enumerate(bar_data):
        x1 = bar_area_left + i * (bar_width + bar_gap)
        x2 = x1 + bar_width
        bar_height = int(max_bar_height * height_pct)
        y1 = bar_area_bottom - bar_height
        y2 = bar_area_bottom

        bar_radius = max(1, bar_width // 3)
        draw.rounded_rectangle([x1, y1, x2, y2], radius=bar_radius, fill=color)

    return img


def save_multi_size_ico(images_with_sizes, filepath):
    """
    Save multiple image sizes into a single .ico file.
    """
    # Sort by size descending (largest first for best quality)
    images_with_sizes.sort(key=lambda x: x[1], reverse=True)
    images = [img for img, size in images_with_sizes]

    # Save with all sizes
    images[0].save(
        filepath,
        format='ICO',
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:] if len(images) > 1 else []
    )


def main():
    print("Generating LUFS Normalizer icons...")

    # Desktop icon (app_icon.ico) - includes text on larger sizes
    desktop_sizes = [16, 24, 32, 48, 64, 128, 256]
    desktop_images = []

    for size in desktop_sizes:
        # Include text only on larger sizes
        include_text = size >= 48
        img = create_lufs_meter_icon(size, include_text=include_text)
        desktop_images.append((img, size))

    save_multi_size_ico(desktop_images, "app_icon.ico")
    print("  Created: app_icon.ico (desktop/executable icon)")

    # Taskbar icon (taskbar_icon.ico) - simple, no text
    taskbar_sizes = [16, 24, 32, 48, 64]
    taskbar_images = []

    for size in taskbar_sizes:
        img = create_simple_meter_icon(size)
        taskbar_images.append((img, size))

    save_multi_size_ico(taskbar_images, "taskbar_icon.ico")
    print("  Created: taskbar_icon.ico (window/taskbar icon)")

    # Also save a PNG version for potential use with iconphoto
    taskbar_images[0][0].save("taskbar_icon.png", format='PNG')
    print("  Created: taskbar_icon.png (PNG fallback)")

    print("\nDone! Use these with PyInstaller:")
    print('  pyinstaller --onefile --noconsole --icon=app_icon.ico --name "LUFS_Normalizer" --add-data "config.json;." --add-data "taskbar_icon.ico;." normalize_gui_modern.py')


if __name__ == "__main__":
    main()
