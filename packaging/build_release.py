#!/usr/bin/python3
"""Build the Ubuntu package, user-installable source archive and checksums."""
import argparse
import gzip
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from install import CATALOG, GTK, ICON, MODULES, install
from app_info import VERSION


def sources():
    yield from (ROOT / name for name in ("install.py", "LICENSE", "README.md", "README.zh-CN.md",
                                          "CHANGELOG.md", "docs/guide.md", "docs/guide.zh-CN.md",
                                          "examples/demo.xml", "packaging/branchxml.sh",
                                          "packaging/branchxml.desktop.in", "packaging/build_release.py",
                                          "packaging/test-wayland.sh", "packaging/smoke_desktop.py"))
    yield from sorted((ROOT / "docs/screenshots").glob("*.png"))
    yield from sorted((ROOT / "docs/screenshots").glob("*.gif"))
    yield from (GTK / (name + ".py") for name in MODULES)
    yield from sorted(GTK.glob("test_*.py"))
    yield GTK / ICON
    yield GTK / CATALOG
    yield (GTK / CATALOG).with_suffix(".po")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    out = parser.parse_args().output.resolve()
    os.umask(0o022)  # Package directories must have the same permissions on every builder.
    out.mkdir(parents=True, exist_ok=True)
    archive = f"branchxml-{VERSION}.tar.gz"
    deb = f"branchxml_{VERSION}_all.deb"
    # A fixed release epoch produces identical binaries from checkouts and tarballs.
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "1795651200"))  # 0.1.0 release date in UTC
    with TemporaryDirectory(dir=out) as temp:
        stage = Path(temp)
        image = stage / "package"
        install(Path("/usr"), image, Path("/usr/bin/python3"))
        control = image / "DEBIAN/control"
        control.parent.mkdir()
        control.write_text(f"""Package: branchxml
Version: {VERSION}
Architecture: all
Section: editors
Priority: optional
Maintainer: BranchXML contributors <206505197+hqy2435662352@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0 (>= 4.12), python3-pygments, python3-lxml, hicolor-icon-theme
Homepage: https://github.com/hqy2435662352/branchxml
Description: Tree-based XML editor for Ubuntu
 Edit XML nodes and values with undo, XPath search and local XSD validation.
""")
        subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(image), str(stage / deb)],
                       check=True, env={**os.environ, "SOURCE_DATE_EPOCH": str(epoch)})
        with (stage / archive).open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=epoch) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as tar:
                for file in sorted(sources()):
                    info = tar.gettarinfo(str(file), arcname=f"branchxml-{VERSION}/{file.relative_to(ROOT)}")
                    info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    info.mtime = epoch
                    info.mode = 0o755 if file.name in ("install.py", "build_release.py", "test-wayland.sh") else 0o644
                    with file.open("rb") as stream:
                        tar.addfile(info, stream)
        sums = "".join(hashlib.sha256((stage / name).read_bytes()).hexdigest() + "  " + name + "\n"
                       for name in (deb, archive))
        (stage / "SHA256SUMS").write_text(sums)
        for name in (deb, archive, "SHA256SUMS"):
            (stage / name).replace(out / name)
            print(out / name)


if __name__ == "__main__":
    main()
