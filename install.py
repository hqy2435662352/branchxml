#!/usr/bin/python3
"""Install or uninstall BranchXML under a user prefix, or stage a system package."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parent
GTK = ROOT / "prototypes/gtk"
sys.path.insert(0, str(GTK))
from app_info import APP_ID

MODULES = ("app_info", "appearance", "branchxml", "chrome", "comparison", "document", "i18n", "inspector",
           "source_view", "tree_find", "xml_tools")
ICON = Path("icons/hicolor/512x512/apps") / (APP_ID + ".png")
CATALOG = Path("locale/zh_CN/LC_MESSAGES/branchxml.mo")


def installed_files(prefix, python):
    app = Path("share/branchxml")
    for module in MODULES:
        filename = module + ".py"
        yield app / filename, (GTK / filename).read_bytes(), 0o644
    yield app / CATALOG, (GTK / CATALOG).read_bytes(), 0o644
    yield Path("share") / ICON, (GTK / ICON).read_bytes(), 0o644
    yield app / "examples/demo.xml", (ROOT / "examples/demo.xml").read_bytes(), 0o644
    yield Path("share/doc/branchxml/copyright"), (ROOT / "LICENSE").read_bytes(), 0o644
    wrapper = (ROOT / "packaging/branchxml.sh").read_text().replace("@PYTHON@", shlex.quote(str(python)))
    yield Path("bin/branchxml"), wrapper.encode(), 0o755
    command = str(prefix / "bin/branchxml")
    quoted = "".join("\\" + ch if ch in '\\"$`' else ch for ch in command)
    quoted = '"' + quoted.replace("\\", "\\\\").replace("%", "%%") + '"'
    desktop = (ROOT / "packaging/branchxml.desktop.in").read_text()
    desktop = desktop.replace("@COMMAND@", quoted).replace("@APP_ID@", APP_ID)
    yield Path("share/applications") / (APP_ID + ".desktop"), desktop.encode(), 0o644


def refresh(prefix):
    for program, args in (("update-desktop-database", [prefix / "share/applications"]),
                          ("gtk-update-icon-cache", ["-f", "-t", prefix / "share/icons/hicolor"])):
        if shutil.which(program):
            subprocess.run([program, *args], check=False, stdout=subprocess.DEVNULL)


def install(prefix, destdir, python, uninstall=False):
    base = destdir / prefix.relative_to("/") if destdir else prefix
    files = list(installed_files(prefix, python))
    if uninstall:
        for rel, _, _ in files:
            (base / rel).unlink(missing_ok=True)
        appdir = base / "share/branchxml"
        for cache in (appdir / "__pycache__").glob("*.pyc"):
            if cache.name.split(".")[0] in MODULES:
                cache.unlink()
        dirs = {appdir, appdir / "__pycache__", base / "share/doc/branchxml"}
        for rel, _, _ in files:
            dirs.update(parent for parent in (base / rel).parents if parent.is_relative_to(appdir))
        for folder in sorted(dirs, key=lambda d: len(d.parts), reverse=True):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
    else:
        for rel, content, mode in files:
            path = base / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                try:
                    stream.write(content)
                    stream.flush()
                    os.fchmod(stream.fileno(), mode)
                    os.replace(stream.name, path)
                finally:
                    Path(stream.name).unlink(missing_ok=True)
    if not destdir:
        refresh(prefix)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    parser.add_argument("--destdir", type=Path, help="stage files for a package")
    parser.add_argument("--python", type=Path, default=Path("/usr/bin/python3"), help="runtime Python interpreter")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args()
    prefix = args.prefix.expanduser().absolute()
    python = args.python.expanduser().absolute()
    if not args.uninstall and not args.destdir:
        probe = ("import gi, pygments, lxml.etree; gi.require_version('Gtk','4.0'); "
                 "from gi.repository import Gtk; raise SystemExit(bool(Gtk.check_version(4,12,0)))")
        if not python.is_file() or subprocess.run([python, "-c", probe]).returncode:
            parser.exit(1, "BranchXML requires GTK 4.12+, PyGObject, Pygments and lxml. See README.md for the Ubuntu packages.\n")
    install(prefix, args.destdir, python, args.uninstall)
    print(("Removed" if args.uninstall else "Installed") + f" BranchXML under {prefix}")


if __name__ == "__main__":
    main()
