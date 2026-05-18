"""
PyInstaller hook for Apple's MLX framework.

MLX ships compiled Metal shader libraries (.metallib) and dynamic
libraries (.dylib) that PyInstaller's default scanning may miss. This
hook collects all of them explicitly.
"""
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

datas = collect_data_files('mlx', include_py_files=False)
binaries = collect_dynamic_libs('mlx')
hiddenimports = collect_submodules('mlx')

# Belt-and-suspenders: walk the package directory and grab any .metallib
# files the helpers above may have missed (they sometimes do for novel
# file extensions).
try:
    import mlx as _mlx
    pkg_dir = Path(_mlx.__file__).resolve().parent
    for metallib in pkg_dir.rglob('*.metallib'):
        rel_dest = metallib.parent.relative_to(pkg_dir.parent)
        datas.append((str(metallib), str(rel_dest)))
except Exception:
    # Don't crash the build if mlx isn't importable in the hook context.
    pass
