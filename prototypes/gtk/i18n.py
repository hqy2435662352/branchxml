"""BranchXML interface language and per-user preference."""

import gettext
import re
from pathlib import Path

from gi.repository import GLib


CHOICES = {"system": "System Default", "en": "English", "zh_CN": "简体中文"}
LOCALE_DIR = Path(__file__).with_name("locale")


def preference_file():
    return Path(GLib.get_user_config_dir()) / "branchxml" / "language"


def read_preference():
    try:
        choice = preference_file().read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return "system"
    return choice if choice in CHOICES else "system"


def catalog_for(choice):
    if choice == "system":
        choice = "en"
        for name in GLib.get_language_names():
            base = re.split(r"[-_@.]", name.lower(), maxsplit=1)[0]
            if base in ("en", "c", "posix"):
                break
            if base == "zh":
                choice = "zh_CN"
                break
    return gettext.translation("branchxml", LOCALE_DIR, languages=[choice], fallback=True)


preference = read_preference()
_catalog = catalog_for(preference)


def select_language(choice):
    global preference, _catalog
    if choice not in CHOICES:
        raise ValueError(choice)
    catalog = catalog_for(choice)
    path = preference_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    GLib.file_set_contents(str(path), (choice + "\n").encode("ascii"))
    preference, _catalog = choice, catalog


def tr(message, **values):
    text = _catalog.gettext(message) if message else ""
    return text.format(**values) if values else text
