# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

# babelfish (dati lingua/paese usati da guessit) e guessit (config JSON +
# tabella TLD) non hanno un hook PyInstaller community: senza i loro datas
# l'app va in crash al primo parsing di un nome file (FileNotFoundError su
# babelfish/data/iso-3166-1.txt), verificato con una build reale.
datas = [('VERSION', '.'), ('resources', 'resources'), ('ffmpeg', 'ffmpeg')]
datas += collect_data_files('babelfish')
datas += collect_data_files('guessit', excludes=['**/test/**'])

# babelfish carica i suoi converter lingua/paese con importlib.import_module()
# dinamico (stringhe in language.py/country.py), non con import statici: senza
# elencarli qui esplicitamente PyInstaller non li impacchetta (ModuleNotFoundError
# su babelfish.converters.alpha2 al primo utilizzo, verificato con una build reale).
babelfish_hiddenimports = [
    'babelfish.converters.alpha2',
    'babelfish.converters.alpha3b',
    'babelfish.converters.alpha3t',
    'babelfish.converters.name',
    'babelfish.converters.scope',
    'babelfish.converters.type',
    'babelfish.converters.opensubtitles',
    'babelfish.converters.countryname',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=babelfish_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Gestore_Film_Portable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
