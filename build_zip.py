"""
Builds dist/aniseed_blender.zip from the add-on folder, ready to install with
Blender's Edit > Preferences > Add-ons > Install from Disk.

The zip holds the aniseed_blender folder itself. Python caches are left out,
as are the PySide6 builds qshake downloads per Blender version (the add-on
offers to download PySide6 the first time it is enabled). Linked folders,
such as vendor modules linked to their own checkouts, are followed, so the
zip always holds real files.

Run it with any Python 3:

    python build_zip.py [output zip]
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.join(ROOT, "addons", "aniseed_blender")
DEFAULT_OUTPUT = os.path.join(ROOT, "dist", "aniseed_blender.zip")

SKIP_DIRS = {"__pycache__", ".git", ".idea"}
SKIP_EXTENSIONS = {".pyc", ".pyo", ".blend1"}


def build(addon: str = ADDON, output: str = DEFAULT_OUTPUT) -> int:
    """
    Zips the add-on folder into the output zip, replacing it.

    Returns:
        The number of files written.
    """
    base = os.path.dirname(addon)
    count = 0

    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for root, dirs, files in os.walk(addon, followlinks=True):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)

            # -- qshake/_vendor keeps only its pure python "general" folder
            if os.path.basename(root) == "_vendor" and os.path.basename(os.path.dirname(root)) == "qshake":
                dirs[:] = [d for d in dirs if d == "general"]

            for name in sorted(files):
                if os.path.splitext(name)[1].lower() in SKIP_EXTENSIONS:
                    continue

                path = os.path.join(root, name)

                # -- Zip paths always use forward slashes
                archive.write(path, os.path.relpath(path, base).replace(os.sep, "/"))
                count += 1

    return count


if __name__ == "__main__":
    output = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    count = build(output=output)
    print(f"Wrote {count} files to {output} ({os.path.getsize(output) / 1024:.0f} KB)")
