# Building from source

The repository contains the compatibility toolkit and RCS Explorer source,
required compact patch recipes/configuration references, and licensed runtime
wrappers. Complete original game executables and game archives are not included.
The separate native engine reconstruction and private research recordings are
outside this repository.

## Run with Python

Use 64-bit Python 3.12 on Windows with Tcl/Tk installed. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python tools/portable_entry.py --launcher
```

For RCS Explorer, use `python tools/portable_entry.py --viewer`. If direct script
execution cannot find the package, set `$env:PYTHONPATH = (Get-Location).Path`,
or use `python -m davilex.entry --launcher` / `--viewer` instead.

The source checkout uses `resources/`; a compiled application uses
`_internal/resources/`. Both reconstruct supported compatibility images from
the user's own game executables, in memory, after validating their hashes.

## Build Windows executables

```powershell
python -m pip install -r tools/packaging/requirements-build.txt
python tools/build_from_checkout.py
```

The result is `dist/Davilex Toolkit/`. Keep the whole folder together. The build
uses PyInstaller's directory layout with UPX disabled and includes both launcher
executables, assets and license notices. It needs no installed games to compile.
It does not download or regenerate game content. Builds are unsigned; a byte-for-byte
match with a release is not promised across Python/compiler/dependency versions.

## Native helpers

`native/hud_scale.cpp` is the original toolkit's HUD helper and
`native/android_colourkey.cpp` is its Wine texture-conversion helper. Reviewed
compiled helpers are supplied as resources. Their source is included so they can
be inspected and rebuilt; the distributed third-party wrappers have upstream
source links in CREDITS.md.

From an **x86 MSVC Developer Command Prompt**, with Python on PATH:

```text
python tools/rebuild_native_helpers.py hud
python tools/rebuild_native_helpers.py colourkey
```

Outputs go to `.cache/native-build/`. HUD helpers report whether they match the
bundled bytes. The colour-key DLL is pinned by hash in `davilex/windowed.py`;
a different reviewed build requires updating that hash and the resource together.
Helpers are not automatically substituted into game executables by the build.

## Tests

The complete development suite contains tests that require private captured
game fixtures. Those copyrighted fixtures are not included, so running every
test in a fresh checkout will not pass without recreating the fixtures.

A fixture-free subset can be run from the repository root:

```powershell
python -c "from pathlib import Path; Path('work').mkdir(exist_ok=True)"
python -m unittest discover -s tests -p test_rcs.py
python -m unittest discover -s tests -p test_mesh.py
python -m unittest discover -s tests -p test_textures.py
python -m unittest discover -s tests -p test_ingredients.py
```

The release passed 206 development tests and a packaged integration check
covering seven supplied games, 44 archives, three textured models and audio
decoding. This is not a claim that every edition, track or play mode is covered.
