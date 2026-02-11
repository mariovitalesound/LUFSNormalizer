#!/usr/bin/env python3
"""
LUFS Normalizer Icon Generator
Creates a professional .ico file for the application

Run this once to generate the icon:
    python create_icon.py

Then rebuild with build.bat
"""

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow not installed. Installing...")
    import subprocess
    subprocess.check_call(['pip', 'install', 'Pillow'])
    from PIL import Image, ImageDraw, ImageFont

import os


def create_lufs_icon():
    """Create a professional LUFS meter-style icon"""
    
    # Icon sizes needed for .ico file
    sizes = [256, 128, 64, 48, 32, 16]
    images = []
    
    for size in sizes:
        # Create image with transparent background
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Calculate proportions
        margin = size // 8
        bar_width = (size - margin * 2) // 5
        bar_gap = bar_width // 4
        
        # Background circle (dark gray)
        draw.ellipse(
            [margin//2, margin//2, size - margin//2, size - margin//2],
            fill=(30, 30, 35, 255)
        )
        
        # Draw VU meter bars (like an audio meter)
        bar_heights = [0.4, 0.6, 0.85, 0.95, 0.7]  # Varying heights
        bar_colors = [
            (46, 204, 113),   # Green
            (46, 204, 113),   # Green
            (241, 196, 15),   # Yellow
            (231, 76, 60),    # Red
            (46, 204, 113),   # Green
        ]
        
        bar_bottom = size - margin - size//6
        max_bar_height = size - margin * 3
        
        for i, (height_pct, color) in enumerate(zip(bar_heights, bar_colors)):
            x = margin + i * (bar_width + bar_gap)
            bar_height = int(max_bar_height * height_pct)
            y_top = bar_bottom - bar_height
            
            # Draw bar with slight rounded corners effect
            draw.rectangle(
                [x, y_top, x + bar_width - bar_gap, bar_bottom],
                fill=color
            )
        
        # Add "LU" text at bottom for larger sizes
        if size >= 48:
            try:
                # Try to use a system font
                font_size = size // 5
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    try:
                        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
                    except:
                        font = ImageFont.load_default()
                
                text = "LU"
                # Get text bounding box
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_x = (size - text_width) // 2
                text_y = size - margin - font_size
                
                # Draw text with slight shadow for depth
                draw.text((text_x + 1, text_y + 1), text, fill=(0, 0, 0, 128), font=font)
                draw.text((text_x, text_y), text, fill=(255, 255, 255, 230), font=font)
            except Exception as e:
                pass  # Skip text if font issues
        
        images.append(img)
    
    # Save as .ico file with all sizes
    icon_path = 'lufs_icon.ico'
    images[0].save(
        icon_path,
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    
    print(f"✅ Icon created: {icon_path}")
    print(f"   Sizes included: {sizes}")
    print(f"\nNow run build.bat to compile with the new icon!")
    
    return icon_path


def create_simple_icon():
    """Fallback: Create a simple colored square icon if fancy one fails"""
    sizes = [256, 128, 64, 48, 32, 16]
    images = []
    
    for size in sizes:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Simple gradient-style meter icon
        margin = size // 10
        
        # Dark background rounded rectangle
        draw.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=size // 8,
            fill=(25, 25, 30, 255)
        )
        
        # Three vertical bars (green, yellow, red)
        bar_width = (size - margin * 4) // 3
        colors = [(46, 204, 113), (241, 196, 15), (231, 76, 60)]
        heights = [0.7, 0.5, 0.3]
        
        for i, (color, h) in enumerate(zip(colors, heights)):
            x = margin * 2 + i * (bar_width + margin // 2)
            bar_height = int((size - margin * 4) * h)
            y = size - margin * 2 - bar_height
            
            draw.rectangle(
                [x, y, x + bar_width - margin // 2, size - margin * 2],
                fill=color
            )
        
        images.append(img)
    
    icon_path = 'lufs_icon.ico'
    images[0].save(
        icon_path,
        format='ICO',
        sizes=[(s, s) for s in sizes],
        append_images=images[1:]
    )
    
    print(f"✅ Simple icon created: {icon_path}")
    return icon_path


if __name__ == '__main__':
    print("LUFS Normalizer - Icon Generator")
    print("=" * 40)
    
    try:
        create_lufs_icon()
    except Exception as e:
        print(f"Fancy icon failed ({e}), creating simple version...")
        create_simple_icon()
