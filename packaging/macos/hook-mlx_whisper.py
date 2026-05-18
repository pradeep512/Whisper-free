"""
PyInstaller hook for mlx-whisper.

Ensures the tokenizer assets, mel filter banks, and submodules bundled
inside the mlx_whisper package are collected into the .app.
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files('mlx_whisper')
hiddenimports = collect_submodules('mlx_whisper')
