# Credits and third-party notices

Davilex Toolkit is a preservation and compatibility project by **MissingThePixel**.
Development, reverse-engineering and tooling assistance: **OpenAI Codex**.
Thanks to the players and testers who helped check Windows, CrossOver and Winlator behaviour.

The original games, artwork, audio, names and other game content belong to their
respective rights holders. This is an independent project and is not affiliated
with or endorsed by Davilex. Game content is not included in the public download.

The MIT license applies to original Davilex Toolkit code. It does not relicense
the original games, third-party libraries, or their embedded components. Their
licenses and notices are retained in the distribution's `licenses` directory.

| Component | Credit / upstream | Purpose and license notice |
| --- | --- | --- |
| DDrawCompat 0.7.2 | [narzoul](https://github.com/narzoul/DDrawCompat) | Windows graphics compatibility; permissive license in `licenses/DDrawCompat.txt`. |
| DXWrapper 1.9.8700.25 | [Elisha Riedlinger and contributors](https://github.com/elishacloud/dxwrapper) | DirectDraw/Direct3D to D3D9; project and embedded-component licenses in `licenses/DXWrapper-License.txt`. |
| Xidi 5.0.0 | [Samuel Grossman and contributors](https://github.com/samuelgr/Xidi) | XInput to legacy input; BSD 3-Clause license in `licenses/Xidi.txt`. Boost, Hookshot and XstdBitSet notices are also included. |
| Python | [Python Software Foundation and contributors](https://www.python.org/) | Application runtime; `licenses/Python.txt`. |
| Tcl/Tk | [Tcl/Tk contributors](https://www.tcl-lang.org/) | Desktop interface; `licenses/Tcl-Tk/`. |
| Pillow | [Pillow contributors](https://python-pillow.org/) | Image decoding and previews; `licenses/Pillow/`. |
| NumPy | [NumPy contributors](https://numpy.org/) | Mesh and image calculations; `licenses/numpy/`, including bundled numerical-library notices. |
| miniaudio Python bindings | [Irmen de Jong](https://github.com/irmen/pyminiaudio) | Audio decoding; MIT license in `licenses/miniaudio-1.61-LICENSE.txt`, including credits to David Reid and Sean Barrett. |
| CFFI / pycparser | [CFFI](https://cffi.readthedocs.io/) / [Eli Bendersky and contributors](https://github.com/eliben/pycparser) | Audio binding support; respective license files in `licenses/`. |
| PyInstaller | [PyInstaller contributors](https://pyinstaller.org/) | Executable packaging; GPL with bootloader exception, `licenses/PyInstaller.txt`. |

dgVoodoo by Dege and FFmpeg were used in earlier investigations. Neither is
bundled in the public release. An optional, separately supplied FFmpeg executable
can be used for audio formats unsupported by the built-in decoder.
