"""User theme preference and system color-scheme tracking."""

from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk


CHOICES = {"system": "System Default", "light": "Light", "dark": "Dark"}


def preference_file():
    return Path(GLib.get_user_config_dir()) / "branchxml" / "theme"


def read_preference():
    try:
        choice = preference_file().read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return "system"
    return choice if choice in CHOICES else "system"


def save_preference(choice):
    if choice not in CHOICES:
        raise ValueError(choice)
    path = preference_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    GLib.file_set_contents(str(path), (choice + "\n").encode("ascii"))


def theme_name_for_scheme(name, dark):
    if not dark and name and name.casefold().endswith("-dark"):
        light_name = name[:-5]
        locations = [Path.home() / ".themes"]
        locations.extend(Path(directory) / "themes" for directory in GLib.get_system_data_dirs())
        locations.append(Path(GLib.get_user_data_dir()) / "themes")
        for themes in locations:
            directory = themes / light_name / "gtk-4.0"
            if (directory / "gtk.css").exists() or (directory / "gtk.gresource").exists():
                return light_name
        return "Default"
    return name


def system_dark(settings, desktop, theme_name=None):
    prop = settings.find_property("gtk-interface-color-scheme")
    if prop is not None:
        scheme = settings.get_property("gtk-interface-color-scheme")
        if scheme.name == "DARK":
            return True
        if scheme.name == "LIGHT":
            return False
    if desktop is not None:
        scheme = desktop.get_string("color-scheme")
        if scheme == "prefer-dark":
            return True
        if scheme == "prefer-light":
            return False
    name = theme_name or settings.get_property("gtk-theme-name") or ""
    return "dark" in name.casefold()


class ThemeManager:
    def __init__(self, callback):
        self.callback = callback
        self.preference = read_preference()
        self.settings = Gtk.Settings.get_default()
        self.original_dark = self.settings.get_property("gtk-application-prefer-dark-theme")
        self.system_theme_name = self.settings.get_property("gtk-theme-name") or "Default"
        self.desktop = self._desktop_settings()
        self.handlers = []
        if self.desktop is not None:
            for key in ("color-scheme", "gtk-theme"):
                if key in self.desktop.get_property("settings-schema").list_keys():
                    self.handlers.append((self.desktop, self.desktop.connect("changed::" + key,
                                                                             self._system_changed)))
        if self.settings.find_property("gtk-interface-color-scheme") is not None:
            self.handlers.append((self.settings, self.settings.connect("notify::gtk-interface-color-scheme",
                                                                        self._system_changed)))
        self.handlers.append((self.settings, self.settings.connect("notify::gtk-theme-name", self._system_changed)))
        self.applying = False
        self.dark = self._effective_dark()
        self._apply_native()

    @staticmethod
    def _desktop_settings():
        source = Gio.SettingsSchemaSource.get_default()
        schema = source.lookup("org.gnome.desktop.interface", True) if source else None
        return Gio.Settings.new_full(schema, None, None) if schema and "color-scheme" in schema.list_keys() else None

    def _system_changed(self, source, detail):
        if self.applying:
            return
        if source is self.settings and detail.name == "gtk-theme-name":
            self.system_theme_name = self.settings.get_property("gtk-theme-name") or ""
        elif source is self.desktop and detail == "gtk-theme":
            self.system_theme_name = self.desktop.get_string("gtk-theme")
        dark = self._effective_dark()
        changed = dark != self.dark
        self.dark = dark
        self._apply_native()
        if changed and self.preference == "system":
            self.callback(self)

    def _effective_dark(self):
        if self.preference == "system":
            return system_dark(self.settings, self.desktop, self.system_theme_name)
        return self.preference == "dark"

    def _apply_native(self):
        self.applying = True
        try:
            theme_name = theme_name_for_scheme(self.system_theme_name, self.dark)
            if theme_name != self.settings.get_property("gtk-theme-name"):
                self.settings.set_property("gtk-theme-name", theme_name)
            self.settings.set_property("gtk-application-prefer-dark-theme", self.dark)
        finally:
            self.applying = False

    def set_preference(self, choice):
        if choice not in CHOICES:
            raise ValueError(choice)
        if choice == self.preference:
            return
        save_preference(choice)
        self.preference = choice
        self.dark = self._effective_dark()
        self._apply_native()
        self.callback(self)

    def close(self):
        for source, handler in self.handlers:
            if source.handler_is_connected(handler):
                source.disconnect(handler)
        self.handlers.clear()
        if self.settings.get_property("gtk-theme-name") != self.system_theme_name:
            self.settings.set_property("gtk-theme-name", self.system_theme_name)
        self.settings.set_property("gtk-application-prefer-dark-theme", self.original_dark)
