# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller (--onedir) per Gestore Film Portable.

ffmpeg/ e resources/ vengono copiati come 'datas' cosi' PyInstaller li piazza
accanto all'exe dentro la cartella dist (file loose, non impacchettati nel
bootloader) — necessario perche' ffmpeg.exe/ffprobe.exe vanno invocati come
processi esterni con un path reale su disco.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

progetto_root = Path(SPECPATH).parent

# babelfish (dipendenza di guessit) carica dati di localizzazione (iso-3166-1.txt
# etc.) via pkg_resources/importlib.resources, e risolve i suoi converter
# (alpha2, alpha3b, ...) via importlib.metadata entry-points dinamici: servono
# sia i moduli (hiddenimports) sia il dist-info con entry_points.txt (copy_metadata).
datas_dati_pacchetti = collect_data_files('babelfish') + collect_data_files('guessit') + copy_metadata('babelfish')
import_nascosti = collect_submodules('babelfish.converters')

a = Analysis(
    [str(progetto_root / 'main.py')],
    pathex=[str(progetto_root)],
    binaries=[],
    datas=[
        (str(progetto_root / 'resources'), 'resources'),
        (str(progetto_root / 'ffmpeg'), 'ffmpeg'),
    ] + datas_dati_pacchetti,
    hiddenimports=import_nascosti,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GestoreFilmPortable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='GestoreFilmPortable',
)
