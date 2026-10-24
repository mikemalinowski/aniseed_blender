# vendor

Copies of aniseed and every module it needs in Blender, bundled so the add-on
works as soon as it is installed. The add-on puts this folder at the front of
`sys.path`, so these copies are used even if another copy of any of them is
importable.

| Module | Copied from | Path in that repository | Commit |
|---|---|---|---|
| `aniseed` | https://github.com/mikemalinowski/aniseed | `aniseed_maya/scripts/aniseed` | `5a46bcb` + local changes |
| `xstack` | https://github.com/mikemalinowski/xstack | `xstack` | `051abaa` + local changes |
| `crosswalk` | https://github.com/mikemalinowski/crosswalk | `crosswalk` | `2b9dfe6` + local changes |
| `qtility` | https://github.com/mikemalinowski/qtility | `qtility` | `1f7080a` + local changes |
| `factories` | https://github.com/mikemalinowski/factories | `factories` | `a992c34` + local changes |
| `signalling` | https://github.com/mikemalinowski/signalling | `signalling` | `c80a499` + local changes |
| `scribble` | https://github.com/mikemalinowski/scribble | `scribble` | `82768dd` + local changes |
| `qshake` | qshake (not yet in a git repository) | `qshake` | — |

Copied on 2026-10-23, from working copies which had uncommitted changes, so
the commits above are the closest commit rather than an exact match.
`aniseed` and `xstack` were copied again later the same day, to pick up the
package manager (Edit > Packages, and the `enabled_by_default` package flag).

`Qt.py` and `blackout.py` are not copied separately: qshake already bundles
them in `qshake/_vendor/general`, and adds that folder to the path once
PySide6 is installed.

## PySide6

PySide6 is not bundled, as it is large and each Blender version needs its own
build. `qshake.install_pyside()` (which the add-on runs from
**Aniseed > Install PySide6**) downloads it into
`qshake/_vendor/<platform>/<blender version>`. Those folders are ignored by
git, so a local install is never committed.

## Updating

These are plain copies, updated by hand. To update one, replace its folder
with a fresh copy of the module from its repository, leaving out
`__pycache__` folders (and, for qshake, any `_vendor/<platform>` folders),
then update the table above.
