#!/usr/bin/env python3
"""
LUFS Normalizer GUI v2.9.1 - Professional Edition

Changes in v2.9.1:
- BUGFIX: Core engine v2.5.1 integration (LUFS meter sample rate fix)

Changes in v2.9.0:
- STRICT PRESET MATCHING: Changing Peak Ceiling now instantly updates preset highlighting.
- LIVE VALIDATION: Preset matching happens on every keystroke (no Enter needed).
- LOGIC FIX: Highlights only appear if BOTH LUFS and Peak match the preset exactly.

Author: Mario Vitale
"""
import customtkinter as ctk
from tkinter import filedialog, messagebox
import json
import threading
from pathlib import Path
import sys
import os

# Import core engine
try:
    from normalize_lufs_core import (
        LUFSNormalizer, apply_lufs_preset, get_preset_for_lufs, get_preset_info,
        VERSION as CORE_VERSION, LUFS_PRESETS, DEFAULT_FAVORITES
    )
except ImportError:
    import normalize_lufs_core
    LUFSNormalizer = normalize_lufs_core.LUFSNormalizer
    apply_lufs_preset = normalize_lufs_core.apply_lufs_preset
    get_preset_for_lufs = normalize_lufs_core.get_preset_for_lufs
    get_preset_info = normalize_lufs_core.get_preset_info
    CORE_VERSION = normalize_lufs_core.VERSION
    LUFS_PRESETS = normalize_lufs_core.LUFS_PRESETS
    DEFAULT_FAVORITES = normalize_lufs_core.DEFAULT_FAVORITES

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

VERSION = "2.9.1"

class CustomDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, message, width=400, height=250):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set() 
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - height) // 2
            self.geometry(f"+{x}+{y}")
        except: pass
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 10))
        msg_label = ctk.CTkLabel(frame, text=message, wraplength=width-40, justify="left", text_color="#cccccc")
        msg_label.pack(fill="both", expand=True)
        ctk.CTkButton(frame, text="OK", width=80, command=self.destroy).pack(pady=(10, 0))
        self.after(50, self.deiconify)

class LUFSNormalizerModernGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"LUFS Normalizer v{VERSION}")
        self.root.geometry("700x850")
        self.root.minsize(680, 750)
        
        if getattr(sys, 'frozen', False): self.app_dir = Path(sys.executable).parent
        else: self.app_dir = Path(__file__).parent
        self.config_file = self.app_dir / 'config.json'
        self.set_window_icon()
        self.config = self.load_config()
        self.normalizer = LUFSNormalizer(config_path=str(self.config_file))
        self.normalizer.set_progress_callback(self.update_progress)
        self.normalizer.set_result_callback(self.handle_file_result)
        
        self.processing = False
        self.processing_lock = threading.Lock()
        self.file_count = 0
        self.log_messages = []
        self.log_window = None
        self.about_window = None
        self.manager_window = None
        self.manager_selected_key = None
        
        # Drag State
        self.drag_window = None
        self.drag_spacer = None
        self.drag_data = {}
        self.favorite_row_widgets = [] 

        self.preset_buttons = {}
        self.selected_preset = self.config.get('preset_name', None)
        self.favorite_presets = self.config.get('favorite_presets', list(DEFAULT_FAVORITES))
        self._setting_preset = False
        self.preset_color_normal = "#2d5a8a"
        self.preset_color_hover = "#3d6a9a"
        self.preset_color_selected = "#1a3d5c"
        
        self.create_widgets()
        self.load_settings_to_ui()
        self.update_file_count()

    def set_window_icon(self):
        """Set the window/taskbar icon (separate from .exe icon)."""
        try:
            icon_path = self.app_dir / 'taskbar_icon.ico'
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
            else:
                # Fallback: try PNG with iconphoto (works on all platforms)
                png_path = self.app_dir / 'taskbar_icon.png'
                if png_path.exists():
                    from PIL import Image, ImageTk
                    img = Image.open(png_path)
                    photo = ImageTk.PhotoImage(img)
                    self.root.iconphoto(True, photo)
                    self._icon_photo = photo  # Keep reference to prevent garbage collection
        except Exception:
            pass  # Silently fail - icon is cosmetic

    def load_config(self):
        default_config = {
            'input_folder': '', 'output_folder': '', 'target_lufs': -24.0, 'peak_ceiling': -2.0,
            'preset_name': 'broadcast_us', 'favorite_presets': list(DEFAULT_FAVORITES),
            'strict_lufs_matching': True, 'auto_open_output': True, 'bit_depth': 'preserve',
            'sample_rate': 'preserve', 'use_batch_folders': True, 'generate_log': True, 'generate_csv': True
        }
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    user_config = json.load(f)
                    if 'preset_name' in user_config:
                        old_to_new = {'broadcast': 'broadcast_eu', 'game': 'game_mobile'}
                        if user_config['preset_name'] in old_to_new: user_config['preset_name'] = old_to_new[user_config['preset_name']]
                    default_config.update(user_config)
            except Exception: pass
        valid_favorites = [p for p in default_config['favorite_presets'] if p in LUFS_PRESETS]
        if not valid_favorites: valid_favorites = list(DEFAULT_FAVORITES)
        default_config['favorite_presets'] = valid_favorites[:5]
        return default_config
    
    def save_config(self):
        self.config.update({
            'input_folder': self.input_var.get(), 'output_folder': self.output_var.get(),
            'target_lufs': float(self.target_var.get()), 'peak_ceiling': float(self.peak_var.get()),
            'preset_name': self.selected_preset if self.selected_preset else '',
            'favorite_presets': self.favorite_presets, 'strict_lufs_matching': self.strict_lufs_var.get(),
            'auto_open_output': self.auto_open_var.get(), 'bit_depth': self.bit_depth_var.get(),
            'sample_rate': self.sample_rate_var.get(), 'use_batch_folders': self.batch_folders_var.get(),
            'generate_log': self.generate_log_var.get(), 'generate_csv': self.generate_csv_var.get()
        })
        try:
            with open(self.config_file, 'w') as f: json.dump(self.config, f, indent=4)
        except Exception as e: print(f"Warning: Could not save config: {e}")
    
    def create_widgets(self):
        self.main_frame = ctk.CTkScrollableFrame(self.root)
        self.main_frame.pack(fill="both", expand=True, padx=15, pady=10)
        
        title_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(title_frame, text="LUFS NORMALIZER", font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        ctk.CTkLabel(title_frame, text=f"v{VERSION}", font=ctk.CTkFont(size=11), text_color="gray").pack(side="left", padx=(8, 0), pady=(6, 0))
        ctk.CTkButton(title_frame, text="ℹ️ About", width=70, height=26, fg_color="transparent", hover_color="#333333", text_color="gray", font=ctk.CTkFont(size=11), command=self.toggle_about).pack(side="right")
        
        io_frame = ctk.CTkFrame(self.main_frame)
        io_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(io_frame, text="Input Folder:", anchor="w").pack(fill="x", padx=12, pady=(12, 3))
        input_row = ctk.CTkFrame(io_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=12)
        self.input_var = ctk.StringVar(value=self.config.get('input_folder', ''))
        self.input_entry = ctk.CTkEntry(input_row, textvariable=self.input_var)
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.input_var.trace('w', lambda *args: self.update_file_count())
        ctk.CTkButton(input_row, text="Browse", width=70, command=self.browse_input).pack(side="right")
        
        ctk.CTkLabel(io_frame, text="Output Folder:", anchor="w").pack(fill="x", padx=12, pady=(10, 3))
        output_row = ctk.CTkFrame(io_frame, fg_color="transparent")
        output_row.pack(fill="x", padx=12, pady=(0, 12))
        self.output_var = ctk.StringVar(value=self.config.get('output_folder', ''))
        self.output_entry = ctk.CTkEntry(output_row, textvariable=self.output_var)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(output_row, text="Browse", width=70, command=self.browse_output).pack(side="right")
        
        presets_frame = ctk.CTkFrame(self.main_frame)
        presets_frame.pack(fill="x", pady=(0, 10))
        presets_header = ctk.CTkFrame(presets_frame, fg_color="transparent")
        presets_header.pack(fill="x", padx=12, pady=(12, 8))
        ctk.CTkLabel(presets_header, text="Favorite Presets", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkButton(presets_header, text="⚙️ Presets Manager", width=140, height=24, fg_color="#444444", hover_color="#555555", font=ctk.CTkFont(size=11), command=self.show_preset_manager).pack(side="right")
        self.presets_row = ctk.CTkFrame(presets_frame, fg_color="transparent")
        self.presets_row.pack(pady=(0, 12))
        self.build_favorite_buttons()
        
        settings_frame = ctk.CTkFrame(self.main_frame)
        settings_frame.pack(fill="x", pady=(0, 10))
        settings_inner = ctk.CTkFrame(settings_frame, fg_color="transparent")
        settings_inner.pack(pady=12)
        ctk.CTkLabel(settings_inner, text="Target LUFS:").grid(row=0, column=0, padx=(0, 5), sticky="e")
        lufs_frame = ctk.CTkFrame(settings_inner, fg_color="transparent")
        lufs_frame.grid(row=0, column=1, padx=(0, 20))
        self.target_var = ctk.StringVar(value=str(self.config.get('target_lufs', -23.0)))
        self.target_entry = ctk.CTkEntry(lufs_frame, textvariable=self.target_var, width=70)
        self.target_entry.pack(side="left")
        self.target_var.trace('w', self.on_manual_entry)
        btn_frame = ctk.CTkFrame(lufs_frame, fg_color="transparent")
        btn_frame.pack(side="left", padx=(2, 0))
        self.lufs_up_btn = ctk.CTkButton(btn_frame, text="▲", width=24, height=16, font=ctk.CTkFont(size=9))
        self.lufs_up_btn.pack(pady=(0, 1))
        self.lufs_up_btn.bind('<Button-1>', lambda e: self.adjust_lufs(0.1 if e.state & 1 else 1.0))
        self.lufs_down_btn = ctk.CTkButton(btn_frame, text="▼", width=24, height=16, font=ctk.CTkFont(size=9))
        self.lufs_down_btn.pack()
        self.lufs_down_btn.bind('<Button-1>', lambda e: self.adjust_lufs(-0.1 if e.state & 1 else -1.0))
        self.target_entry.bind('<Up>', lambda e: self.adjust_lufs(0.1 if e.state & 1 else 1.0))
        self.target_entry.bind('<Down>', lambda e: self.adjust_lufs(-0.1 if e.state & 1 else -1.0))
        
        ctk.CTkLabel(settings_inner, text="Peak Ceiling:").grid(row=0, column=2, padx=(0, 5), sticky="e")
        self.peak_var = ctk.StringVar(value=str(self.config.get('peak_ceiling', -1.0)))
        ctk.CTkEntry(settings_inner, textvariable=self.peak_var, width=60).grid(row=0, column=3, padx=(0, 5))
        self.peak_var.trace('w', self.on_manual_entry) # Live update on peak change
        
        ctk.CTkLabel(settings_inner, text="dBTP", text_color="gray").grid(row=0, column=4)
        
        format_frame = ctk.CTkFrame(self.main_frame)
        format_frame.pack(fill="x", pady=(0, 10))
        format_inner = ctk.CTkFrame(format_frame, fg_color="transparent")
        format_inner.pack(pady=12)
        ctk.CTkLabel(format_inner, text="Bit Depth:").grid(row=0, column=0, padx=(0, 5))
        self.bit_depth_var = ctk.StringVar(value=self.config.get('bit_depth', 'preserve'))
        ctk.CTkOptionMenu(format_inner, variable=self.bit_depth_var, values=['preserve', '16', '24', '32'], width=100).grid(row=0, column=1, padx=(0, 25))
        ctk.CTkLabel(format_inner, text="Sample Rate:").grid(row=0, column=2, padx=(0, 5))
        self.sample_rate_var = ctk.StringVar(value=self.config.get('sample_rate', 'preserve'))
        ctk.CTkOptionMenu(format_inner, variable=self.sample_rate_var, values=['preserve', '44100 Hz', '48000 Hz'], width=110).grid(row=0, column=3)
        
        options_frame = ctk.CTkFrame(self.main_frame)
        options_frame.pack(fill="x", pady=(0, 10))
        options_inner = ctk.CTkFrame(options_frame, fg_color="transparent")
        options_inner.pack(pady=12)
        self.batch_folders_var = ctk.BooleanVar(value=self.config.get('use_batch_folders', True))
        ctk.CTkCheckBox(options_inner, text="Organize output in timestamped batch folders", variable=self.batch_folders_var).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        self.auto_open_var = ctk.BooleanVar(value=self.config.get('auto_open_output', True))
        ctk.CTkCheckBox(options_inner, text="Auto-open output folder when complete", variable=self.auto_open_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=2)
        self.generate_log_var = ctk.BooleanVar(value=self.config.get('generate_log', True))
        ctk.CTkCheckBox(options_inner, text="Generate processing log", variable=self.generate_log_var).grid(row=2, column=0, sticky="w", pady=2, padx=(0, 20))
        self.generate_csv_var = ctk.BooleanVar(value=self.config.get('generate_csv', True))
        ctk.CTkCheckBox(options_inner, text="Generate CSV report", variable=self.generate_csv_var).grid(row=2, column=1, sticky="w", pady=2)
        strict_row = ctk.CTkFrame(options_inner, fg_color="transparent")
        strict_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 2))
        self.strict_lufs_var = ctk.BooleanVar(value=self.config.get('strict_lufs_matching', True))
        strict_cb = ctk.CTkCheckBox(strict_row, text="Strict LUFS matching", variable=self.strict_lufs_var)
        strict_cb.pack(side="left")
        ctk.CTkButton(strict_row, text="?", width=20, height=20, fg_color="#555555", hover_color="#666666", font=ctk.CTkFont(size=10), command=self.show_strict_mode_help).pack(side="left", padx=(5, 0))
        
        process_frame = ctk.CTkFrame(self.main_frame)
        process_frame.pack(fill="x", pady=(0, 10))
        self.file_count_var = ctk.StringVar(value="0 files found")
        ctk.CTkLabel(process_frame, textvariable=self.file_count_var, font=ctk.CTkFont(size=11)).pack(pady=(12, 8))
        self.progress_bar = ctk.CTkProgressBar(process_frame, width=400)
        self.progress_bar.pack(pady=(0, 4))
        self.progress_bar.set(0)
        self.status_var = ctk.StringVar(value="Ready")
        ctk.CTkLabel(process_frame, textvariable=self.status_var, font=ctk.CTkFont(size=11)).pack(pady=(0, 8))
        btn_row = ctk.CTkFrame(process_frame, fg_color="transparent")
        btn_row.pack(pady=(0, 12))
        self.start_btn = ctk.CTkButton(btn_row, text="Start Processing", width=160, height=38, fg_color="#2d8f2d", hover_color="#1f6b1f", command=self.start_processing)
        self.start_btn.pack(side="left", padx=8)
        self.stop_btn = ctk.CTkButton(btn_row, text="Stop", width=80, height=38, fg_color="#8f2d2d", hover_color="#6b1f1f", state="disabled", command=self.stop_processing)
        self.stop_btn.pack(side="left", padx=8)
        self.log_btn = ctk.CTkButton(btn_row, text="📋 Log", width=70, height=38, fg_color="#555555", hover_color="#666666", command=self.toggle_log_window)
        self.log_btn.pack(side="left", padx=8)
        
        footer = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        footer.pack(fill="x", pady=(5, 0))
        ctk.CTkLabel(footer, text=f"Engine v{CORE_VERSION} • True Peak • TPDF Dither • SOXR", font=ctk.CTkFont(size=10), text_color="gray").pack()
    
    def adjust_lufs(self, delta):
        try:
            current = float(self.target_var.get())
            new_value = round(current + delta, 1)
            self.target_var.set(str(new_value))
        except ValueError: pass
        return "break"
    
    def apply_preset(self, preset_name):
        self._setting_preset = True
        lufs, peak = apply_lufs_preset(preset_name)
        self.target_var.set(str(lufs))
        self.peak_var.set(str(peak))
        self._update_preset_buttons(preset_name)
        self.selected_preset = preset_name
        self._setting_preset = False
        self.log_message(f"Applied preset: {preset_name} ({lufs} LUFS)")
    
    def _update_preset_buttons(self, selected_name):
        for name, data in self.preset_buttons.items():
            if name == selected_name:
                data['button'].configure(fg_color=self.preset_color_selected, border_width=3, border_color="white")
            else:
                data['button'].configure(fg_color=self.preset_color_normal, border_width=2, border_color="#4a7ab0")
    
    def on_manual_entry(self, *args):
        if self._setting_preset: return
        
        lufs_str = self.target_var.get()
        peak_str = self.peak_var.get()
        
        try:
            lufs_val = float(lufs_str)
            peak_val = float(peak_str)
            matching_preset = get_preset_for_lufs(lufs_val, peak_val)
        except ValueError:
            matching_preset = None

        if matching_preset:
            self._update_preset_buttons(matching_preset)
            self.selected_preset = matching_preset
        else:
            for name, data in self.preset_buttons.items():
                data['button'].configure(fg_color=self.preset_color_normal, border_width=2, border_color="#4a7ab0")
            self.selected_preset = None

    def build_favorite_buttons(self):
        for name, data in list(self.preset_buttons.items()):
            if 'button' in data: data['button'].destroy()
        self.preset_buttons.clear()
        for preset_key in self.favorite_presets:
            preset = LUFS_PRESETS.get(preset_key)
            if not preset: continue
            label = f"{preset['name']}\n{int(preset['lufs'])} LUFS"
            btn = ctk.CTkButton(self.presets_row, text=label, width=110, height=45, fg_color=self.preset_color_normal, hover_color=self.preset_color_hover, border_width=2, border_color="#4a7ab0", command=lambda p=preset_key: self.apply_preset(p))
            btn.pack(side="left", padx=4)
            self.preset_buttons[preset_key] = {'button': btn}
        if self.selected_preset and self.selected_preset in self.preset_buttons:
            self._update_preset_buttons(self.selected_preset)

    def show_preset_manager(self):
        if self.manager_window and self.manager_window.winfo_exists():
            self.manager_window.lift()
            return

        self.manager_window = ctk.CTkToplevel(self.root)
        self.manager_window.withdraw()
        self.manager_window.title("Preset Manager")
        self.manager_window.geometry("520x720") 
        self.manager_window.transient(self.root)
        self.center_window(self.manager_window, 520, 720)

        main = ctk.CTkFrame(self.manager_window, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(main, text="Preset Manager", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(0, 5))
        ctk.CTkLabel(main, text="Drag ≡ to reorder favorites. Click to select.", text_color="gray").pack(pady=(0, 10))

        ctk.CTkLabel(main, text="⭐ FAVORITES (Top 5 on main screen)", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(5,0))
        self.favorites_list = ctk.CTkScrollableFrame(main, height=200)
        self.favorites_list.pack(fill="x", pady=(5, 15))

        ctk.CTkLabel(main, text="📚 AVAILABLE PRESETS", font=ctk.CTkFont(weight="bold")).pack(anchor="w")
        self.all_presets_list = ctk.CTkScrollableFrame(main, height=220)
        self.all_presets_list.pack(fill="both", expand=True, pady=5)

        btn_frame = ctk.CTkFrame(main, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(15, 0), side="bottom")
        
        self.apply_btn = ctk.CTkButton(btn_frame, text="Apply Selected & Close", width=180, fg_color="#2d8f2d", hover_color="#1f6b1f", command=self.apply_manager_selection)
        self.apply_btn.pack(side="right")
        ctk.CTkButton(btn_frame, text="Close", width=80, fg_color="#555555", hover_color="#666666", command=self.manager_window.destroy).pack(side="right", padx=10)

        self.manager_window.bind("<ButtonRelease-1>", self.stop_lift_drag)

        self.refresh_manager_ui()
        self.manager_window.after(50, self.manager_window.deiconify)

    def refresh_manager_ui(self):
        for widget in self.favorites_list.winfo_children(): widget.destroy()
        self.favorite_row_widgets = []
        for idx, key in enumerate(self.favorite_presets): self.create_favorite_row(key, idx)

        for widget in self.all_presets_list.winfo_children(): widget.destroy()
        sorted_keys = sorted(LUFS_PRESETS.keys())
        for key in sorted_keys:
            if key not in self.favorite_presets: self.create_library_row(key)
        
        if self.manager_selected_key: self.highlight_manager_row(self.manager_selected_key)

    def create_favorite_row(self, key, index):
        preset = LUFS_PRESETS.get(key, {})
        row = ctk.CTkFrame(self.favorites_list, fg_color="transparent")
        row.pack(fill="x", pady=2)
        row.preset_key = key
        self.favorite_row_widgets.append(row)
        
        handle = ctk.CTkLabel(row, text="≡", width=30, font=ctk.CTkFont(size=16), text_color="gray", cursor="hand2")
        handle.pack(side="left", padx=(5,0))
        
        content = ctk.CTkFrame(row, fg_color="transparent")
        content.pack(side="left", fill="x", expand=True)
        
        ctk.CTkLabel(content, text=preset.get('name', key), font=ctk.CTkFont(weight="bold"), anchor="w").pack(side="left", padx=10)
        ctk.CTkLabel(content, text=f"{int(preset.get('lufs'))} LUFS", text_color="gray", anchor="w").pack(side="left")
        
        ctk.CTkButton(row, text="✕", width=30, height=24, fg_color="#444444", hover_color="#666666", command=lambda k=key: self.toggle_favorite(k)).pack(side="right", padx=10)

        handle.bind("<Button-1>", lambda e, k=key, n=preset.get('name', key), w=row: self.start_lift_drag(e, k, n, w))
        handle.bind("<B1-Motion>", self.update_lift_drag)
        for w in [row, content]: w.bind("<Button-1>", lambda e, k=key: self.select_manager_row(k))

    def create_library_row(self, key):
        preset = LUFS_PRESETS.get(key, {})
        row = ctk.CTkFrame(self.all_presets_list, fg_color="transparent")
        row.pack(fill="x", pady=2)
        row.preset_key = key
        ctk.CTkLabel(row, text="", width=35).pack(side="left")
        ctk.CTkLabel(row, text=preset.get('name', key), anchor="w", width=180).pack(side="left", padx=10)
        ctk.CTkLabel(row, text=f"{int(preset.get('lufs'))} LUFS", text_color="gray").pack(side="left")
        ctk.CTkButton(row, text="⭐", width=30, height=24, fg_color="transparent", hover_color="#333333", command=lambda k=key: self.toggle_favorite(k)).pack(side="right", padx=10)
        row.bind("<Button-1>", lambda e, k=key: self.select_manager_row(k))

    def start_lift_drag(self, event, key, name, widget):
        if self.drag_window: self.stop_lift_drag(None)
        self.drag_data["key"] = key
        self.drag_data["offset_x"] = event.x
        self.drag_data["offset_y"] = event.y
        self.drag_data["current_index"] = self.favorite_presets.index(key)
        
        # Insert invisible spacer to hold the gap
        self.drag_spacer = ctk.CTkFrame(self.favorites_list, height=45, fg_color="transparent")
        
        # Hide original (unpack it), but keep reference to repack later
        widget.pack_forget()
        self.repack_list_with_spacer(self.drag_data["current_index"])

        # Create clone
        self.drag_window = ctk.CTkToplevel(self.root)
        self.drag_window.overrideredirect(True)
        self.drag_window.attributes('-topmost', True)
        self.drag_window.attributes('-alpha', 0.9)
        
        f = ctk.CTkFrame(self.drag_window, fg_color="#2d5a8a", border_width=1, border_color="white", corner_radius=6)
        f.pack(fill="both", expand=True)
        
        # Clone internal layout manually for fidelity
        ctk.CTkLabel(f, text="≡", width=30, font=ctk.CTkFont(size=16), text_color="gray").pack(side="left", padx=(5,0))
        ctk.CTkLabel(f, text=name, font=ctk.CTkFont(weight="bold"), text_color="white", anchor="w", width=140).pack(side="left", padx=10)
        
        x = event.x_root - self.drag_data["offset_x"]
        y = event.y_root - self.drag_data["offset_y"]
        self.drag_window.geometry(f"+{x}+{y}")

    def repack_list_with_spacer(self, spacer_index):
        # We need to repack all widgets in correct order, inserting spacer
        # Filter out the widget being dragged (it's already unpacked)
        active_widgets = [w for w in self.favorite_row_widgets if w.preset_key != self.drag_data["key"]]
        
        for w in self.favorites_list.winfo_children(): w.pack_forget()

        # Insert Spacer
        final_list = active_widgets[:spacer_index] + [self.drag_spacer] + active_widgets[spacer_index:]
        for w in final_list:
            w.pack(fill="x", pady=2)

    def update_lift_drag(self, event):
        if not self.drag_window: return
        try:
            # Move ghost
            x = event.x_root - self.drag_data["offset_x"]
            y = event.y_root - self.drag_data["offset_y"]
            self.drag_window.geometry(f"+{x}+{y}")
            
            # Smart Reorder: Calculate Insertion Index based on Y geometry (more stable than hit test)
            mouse_y = event.y_root
            
            # Iterate through all rows (except spacer) to find where we fit
            # We check the middle Y point of each row
            active_widgets = [w for w in self.favorite_row_widgets if w.preset_key != self.drag_data["key"]]
            
            new_index = len(active_widgets) # Default to end
            
            for i, w in enumerate(active_widgets):
                w_y = w.winfo_rooty()
                w_h = w.winfo_height()
                w_mid = w_y + (w_h / 2)
                
                if mouse_y < w_mid:
                    new_index = i
                    break
            
            if new_index != self.drag_data["current_index"]:
                self.drag_data["current_index"] = new_index
                self.repack_list_with_spacer(new_index)
                
        except Exception: pass

    def stop_lift_drag(self, event):
        if self.drag_window:
            self.drag_window.destroy()
            self.drag_window = None
            
            # Apply the move
            target_idx = self.drag_data.get("current_index", 0)
            key = self.drag_data["key"]
            
            if key in self.favorite_presets:
                self.favorite_presets.remove(key)
                self.favorite_presets.insert(target_idx, key)
            
            self.save_config()
            self.build_favorite_buttons()
            self.refresh_manager_ui() # Full rebuild closes the "gap"

    def toggle_favorite(self, key):
        if key in self.favorite_presets:
            if len(self.favorite_presets) > 1: self.favorite_presets.remove(key)
            else:
                CustomDialog(self.manager_window, "Warning", "Keep at least one favorite.")
                return
        else:
            if len(self.favorite_presets) < 5: self.favorite_presets.append(key)
            else:
                CustomDialog(self.manager_window, "Limit", "Max 5 favorites.")
                return
        self.save_config()
        self.build_favorite_buttons()
        self.refresh_manager_ui()

    def select_manager_row(self, key):
        self.manager_selected_key = key
        self.highlight_manager_row(key)
        
    def highlight_manager_row(self, key):
        def color_widgets(parent):
            for row in parent.winfo_children():
                if hasattr(row, 'preset_key'):
                    bg = "#2d5a8a" if row.preset_key == key else "transparent"
                    row.configure(fg_color=bg)
        color_widgets(self.favorites_list)
        color_widgets(self.all_presets_list)

    def apply_manager_selection(self):
        if self.manager_selected_key:
            self.apply_preset(self.manager_selected_key)
        
        # Always close window (User intent: "I'm done")
        if self.manager_window:
            self.manager_window.destroy()
            self.manager_window = None

    def center_window(self, win, width, height):
        x = self.root.winfo_x() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - height) // 2
        win.geometry(f"+{int(x)}+{int(y)}")

    def show_strict_mode_help(self):
        text = ("Strict LUFS: Files exceeding peak are skipped.\n\n"
                "Drift Mode: Gain reduced to protect peak (quieter result).")
        CustomDialog(self.root, "Strict Mode Info", text, height=200)

    def browse_input(self):
        folder = filedialog.askdirectory(title="Select Input Folder", initialdir=self.input_var.get() or str(Path.home()))
        if folder: self.input_var.set(folder)
    
    def browse_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder", initialdir=self.output_var.get() or str(Path.home()))
        if folder: self.output_var.set(folder)
    
    def update_file_count(self):
        input_folder = self.input_var.get()
        if input_folder and Path(input_folder).exists():
            input_path = Path(input_folder)
            wav_files = list(input_path.glob('*.wav')) + list(input_path.glob('*.WAV'))
            aiff_files = (list(input_path.glob('*.aiff')) + list(input_path.glob('*.AIFF')) + list(input_path.glob('*.aif')) + list(input_path.glob('*.AIF')))
            self.file_count = len(wav_files) + len(aiff_files)
            self.file_count_var.set(f"{self.file_count} audio files found")
            self.start_btn.configure(text=f"Start Processing ({self.file_count})")
        else:
            self.file_count = 0
            self.file_count_var.set("No folder selected")
            self.start_btn.configure(text="Start Processing")
    
    def log_message(self, message, is_error=False):
        self.log_messages.append({'text': message, 'is_error': is_error})
        if self.log_window and self.log_window.winfo_exists():
            self._append_to_log_window(message, is_error)
    
    def _append_to_log_window(self, message, is_error=False):
        if hasattr(self, 'log_textbox'):
            self.log_textbox.configure(state="normal")
            if is_error: self.log_textbox.insert("end", message + "\n", "error")
            else: self.log_textbox.insert("end", message + "\n")
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")
    
    def toggle_log_window(self):
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.destroy()
            self.log_window = None
        else: self.show_log_window()
    
    def show_log_window(self, force_show=False):
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.lift()
            return
        self.log_window = ctk.CTkToplevel(self.root)
        self.log_window.withdraw()
        self.log_window.title("Processing Log")
        self.log_window.geometry("600x400")
        self.log_window.transient(self.root)
        self.log_window.protocol("WM_DELETE_WINDOW", self.on_log_window_close)
        self.center_window(self.log_window, 600, 400)
        self.log_textbox = ctk.CTkTextbox(self.log_window, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_textbox.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_textbox.tag_config("error", foreground="#ff5555")
        for msg in self.log_messages:
            if msg['is_error']: self.log_textbox.insert("end", msg['text'] + "\n", "error")
            else: self.log_textbox.insert("end", msg['text'] + "\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")
        btn_frame = ctk.CTkFrame(self.log_window, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(btn_frame, text="Clear Log", width=80, command=self.clear_log).pack(side="left")
        ctk.CTkButton(btn_frame, text="Close", width=80, command=self.log_window.destroy).pack(side="right")
        self.log_window.after(50, self.log_window.deiconify)
    
    def on_log_window_close(self):
        if self.log_window: self.log_window.destroy(); self.log_window = None
    
    def clear_log(self):
        self.log_messages = []
        if hasattr(self, 'log_textbox') and self.log_textbox.winfo_exists():
            self.log_textbox.configure(state="normal")
            self.log_textbox.delete("1.0", "end")
            self.log_textbox.configure(state="disabled")
    
    def update_progress(self, current, total, filename):
        progress = current / total if total > 0 else 0
        self.root.after(0, lambda: self.progress_bar.set(progress))
        self.root.after(0, lambda: self.status_var.set(f"Processing: {filename} ({current}/{total})"))
    
    def handle_file_result(self, filename, status, details):
        if status == 'SUCCESS': msg = f"✓ {filename} | {details}"; is_err = False
        elif status == 'SUCCESS_UNDERSHOOT': msg = f"✓ {filename} | {details} (peak limited)"; is_err = False
        elif status == 'NEEDS_LIMITING': msg = f"⚠ {filename} | {details}"; is_err = True
        elif status == 'SKIPPED': msg = f"⊘ {filename} | {details}"; is_err = False
        elif status == 'BLOCKED': msg = f"✗ {filename} | {details}"; is_err = True
        elif status == 'FAILED': msg = f"❌ {filename} | {details}"; is_err = True
        else: msg = f"{status}: {filename}"; is_err = False
        self.root.after(0, lambda: self.log_message(msg, is_error=is_err))
    
    def validate_inputs(self):
        if not self.input_var.get() or not Path(self.input_var.get()).exists():
            CustomDialog(self.root, "Error", "Please select a valid input folder.")
            return False
        if not self.output_var.get():
            CustomDialog(self.root, "Error", "Please select an output folder.")
            return False
        Path(self.output_var.get()).mkdir(parents=True, exist_ok=True)
        if self.file_count == 0:
            CustomDialog(self.root, "Error", "No audio files found in input folder.")
            return False
        try: float(self.target_var.get()); float(self.peak_var.get())
        except ValueError:
            CustomDialog(self.root, "Error", "Invalid LUFS or Peak value.")
            return False
        return True
    
    def start_processing(self):
        if not self.processing_lock.acquire(blocking=False): return
        try:
            if not self.validate_inputs(): self.processing_lock.release(); return
            self.processing = True
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.progress_bar.set(0)
            self.clear_log()
            self.save_config()
            self.log_message("=" * 50)
            self.log_message(f"LUFS NORMALIZER v{VERSION}")
            self.log_message("=" * 50)
            self.log_message(f"Target: {self.target_var.get()} LUFS")
            self.log_message(f"Peak Ceiling: {self.peak_var.get()} dBTP")
            self.log_message("-" * 50)
            thread = threading.Thread(target=self.run_normalization, daemon=True)
            thread.start()
        except Exception as e:
            self.processing_lock.release()
            CustomDialog(self.root, "Error", f"Failed to start: {e}")
    
    def run_normalization(self):
        try:
            success, total, log_path, csv_path, output_path = self.normalizer.normalize_batch(
                input_dir=self.input_var.get(), output_dir=self.output_var.get(),
                target_lufs=float(self.target_var.get()), peak_ceiling=float(self.peak_var.get()),
                bit_depth=self.bit_depth_var.get(), sample_rate=self.sample_rate_var.get(),
                use_batch_folders=self.batch_folders_var.get(), generate_log=self.generate_log_var.get(),
                generate_csv=self.generate_csv_var.get(), strict_lufs_matching=self.strict_lufs_var.get()
            )
            self.root.after(0, self.processing_complete, success, total, log_path, csv_path, output_path)
        except Exception as e: self.root.after(0, self.processing_error, str(e))
    
    def processing_complete(self, success, total, log_path, csv_path, output_path):
        self.processing = False
        self.processing_lock.release()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.progress_bar.set(1.0)
        self.status_var.set(f"Complete: {success}/{total} files")
        skipped = len(self.normalizer.skipped_files)
        errors = len(self.normalizer.errors)
        has_issues = skipped > 0 or errors > 0 or success < total
        self.log_message("")
        self.log_message("=" * 50)
        self.log_message(f"COMPLETE: {success}/{total} files processed")
        if skipped > 0:
            self.log_message(f"⚠️ NEEDS LIMITING: {skipped} files exceeded peak ceiling", is_error=True)
            self.log_message(f"   → Copied to 'needs_limiting/' folder", is_error=True)
        if errors > 0: self.log_message(f"❌ ERRORS: {errors} files failed", is_error=True)
        self.log_message("=" * 50)
        if has_issues: self.show_log_window(force_show=True)
        if self.auto_open_var.get():
            if output_path:
                if has_issues:
                    CustomDialog(self.root, "Processing Complete", f"Processed {success}/{total} files.\nCheck log for issues.")
                self.open_folder(output_path)
        else:
            if messagebox.askyesno("Processing Complete", f"Processed {success}/{total} files.\nOpen output folder?"):
                self.open_folder(output_path)
    
    def processing_error(self, error_message):
        self.processing = False
        self.processing_lock.release()
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_var.set("Error occurred")
        self.log_message(f"❌ ERROR: {error_message}", is_error=True)
        self.show_log_window(force_show=True)
        CustomDialog(self.root, "Error", f"An error occurred:\n{error_message}")
    
    def stop_processing(self):
        self.normalizer.request_stop()
        self.status_var.set("Stopping...")
        self.log_message("Stop requested...")
    
    def open_folder(self, path):
        try:
            if sys.platform == 'win32': os.startfile(path)
            elif sys.platform == 'darwin': os.system(f'open "{path}"')
            else: os.system(f'xdg-open "{path}"')
        except Exception as e: self.log_message(f"Could not open folder: {e}")
    
    def load_settings_to_ui(self):
        matching_preset = get_preset_for_lufs(self.target_var.get())
        if matching_preset:
            self._update_preset_buttons(matching_preset)
            self.selected_preset = matching_preset
    
    def toggle_about(self):
        if self.about_window and self.about_window.winfo_exists():
            self.about_window.destroy()
            self.about_window = None
        else: self.show_about()
    
    def on_about_window_close(self):
        if self.about_window:
            self.about_window.destroy()
            self.about_window = None
    
    def show_about(self):
        if self.about_window and self.about_window.winfo_exists():
            self.about_window.lift()
            self.about_window.focus()
            return
        self.about_window = ctk.CTkToplevel(self.root)
        self.about_window.withdraw()
        self.about_window.title("About LUFS Normalizer")
        self.about_window.geometry("500x600")
        self.about_window.resizable(False, False)
        self.about_window.transient(self.root)
        self.about_window.protocol("WM_DELETE_WINDOW", self.on_about_window_close)
        x = self.root.winfo_x() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 600) // 2
        self.about_window.geometry(f"+{x}+{y}")
        main = ctk.CTkFrame(self.about_window, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=15)
        ctk.CTkLabel(main, text="LUFS Normalizer", font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(0, 3))
        ctk.CTkLabel(main, text=f"Version {VERSION}", font=ctk.CTkFont(size=11), text_color="gray").pack(pady=(0, 12))
        content = ctk.CTkScrollableFrame(main, height=420)
        content.pack(fill="both", expand=True)
        sections = [
            ("Purpose", "Professional batch audio normalization for broadcast, game audio, and streaming. Normalizes to industry-standard LUFS while respecting True Peak limits."),
            ("Key Features", "• LUFS normalization (ITU-R BS.1770-4)\n• True Peak measurement (dBTP)\n• TPDF dithering\n• SOXR resampling\n• Batch processing\n• 10 presets\n• Strict LUFS or Drift (peak-protect) modes"),
            ("Standards Reference", "• ATSC A/85: -24 LUFS\n• EBU R128: -23 LUFS\n• ASWG-R001: -24/-18 LUFS\n• Apple Podcasts: -16 LUFS\n• Spotify/YouTube: -14 LUFS"),
            ("Peak Handling Modes", "Strict LUFS (default): Skip files exceeding peak. Ensures exact target LUFS.\n\nDrift Mode: Reduce gain to protect peak. Final LUFS may undershoot target."),
            ("Presets", "• Broadcast US/EU\n• Streaming\n• Podcast\n• Game Console/Mobile\n• Film/Cinema\n• Music Dynamic/Loud"),
            ("Keyboard Shortcuts", "• ↑/↓ arrows: Adjust by 1.0\n• Shift + ↑/↓: Adjust by 0.1"),
            ("Credits", "Developed by Mario Vitale")
        ]
        for title, text in sections:
            ctk.CTkLabel(content, text=title, font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x", pady=(8, 2))
            ctk.CTkLabel(content, text=text, font=ctk.CTkFont(size=11), anchor="w", justify="left", wraplength=400).pack(fill="x", pady=(0, 4))
        ctk.CTkButton(main, text="Close", width=90, command=self.on_about_window_close).pack(pady=(12, 0))
        self.about_window.after(50, self.about_window.deiconify)

def main():
    root = ctk.CTk()
    app = LUFSNormalizerModernGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()