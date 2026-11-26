"""Theme preference and system color-scheme tests."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

from theme import ThemeManager, system_dark, theme_name_for_scheme


def gtk_settings(theme_name="Yaru-dark"):
    values = {"gtk-theme-name": theme_name, "gtk-application-prefer-dark-theme": False}
    settings = Mock()
    settings.find_property.return_value = None
    settings.get_property.side_effect = values.__getitem__
    settings.set_property.side_effect = lambda key, value: values.__setitem__(key, value)
    settings.handler_is_connected.return_value = False
    return settings, values


class ColorSchemeTest(unittest.TestCase):
    def test_detects_system_color_scheme(self):
        settings, _ = gtk_settings()
        self.assertTrue(system_dark(settings, None))
        settings.get_property.return_value = "Adwaita"
        self.assertTrue(system_dark(settings, Mock(get_string=Mock(return_value="prefer-dark"))))
        self.assertFalse(system_dark(settings, Mock(get_string=Mock(return_value="prefer-light"))))

    def test_light_override_selects_an_available_variant(self):
        with TemporaryDirectory() as temp:
            theme_dir = Path(temp) / "themes/Yaru/gtk-4.0"
            theme_dir.mkdir(parents=True)
            (theme_dir / "gtk.css").touch()
            with patch.object(GLib, "get_system_data_dirs", return_value=[temp]):
                self.assertEqual(theme_name_for_scheme("Yaru-dark", False), "Yaru")
                self.assertEqual(theme_name_for_scheme("Yaru-dark", True), "Yaru-dark")
                self.assertEqual(theme_name_for_scheme("Unknown-dark", False), "Default")

    def test_gnome_color_scheme_and_theme_survive_an_override(self):
        schema = Gio.SettingsSchemaSource.get_default().lookup("org.gnome.desktop.interface", True)
        desktop = Gio.Settings.new_full(schema, Gio.memory_settings_backend_new(), None)
        desktop.set_string("gtk-theme", "Yaru-dark")
        desktop.set_string("color-scheme", "default")
        with TemporaryDirectory() as temp:
            preference = Path(temp) / "branchxml/theme"
            theme_dir = Path(temp) / "themes/Yaru/gtk-4.0"
            theme_dir.mkdir(parents=True)
            (theme_dir / "gtk.css").touch()
            settings, values = gtk_settings()
            with (patch.object(ThemeManager, "_desktop_settings", return_value=desktop),
                  patch.object(Gtk.Settings, "get_default", return_value=settings),
                  patch("theme.preference_file", return_value=preference),
                  patch.object(GLib, "get_system_data_dirs", return_value=[temp])):
                manager = ThemeManager(lambda *_: None)
                try:
                    self.assertTrue(manager.dark)
                    manager.set_preference("light")
                    self.assertEqual(values["gtk-theme-name"], "Yaru")
                    manager.set_preference("system")
                    self.assertTrue(manager.dark)
                    self.assertEqual(values["gtk-theme-name"], "Yaru-dark")
                    desktop.set_string("color-scheme", "prefer-light")
                    while GLib.MainContext.default().pending():
                        GLib.MainContext.default().iteration(False)
                    self.assertFalse(manager.dark)
                    self.assertEqual(values["gtk-theme-name"], "Yaru")
                finally:
                    manager.close()

    def test_system_fallback_restores_theme_without_gnome_settings(self):
        with TemporaryDirectory() as temp:
            preference = Path(temp) / "branchxml/theme"
            theme_dir = Path(temp) / "themes/Yaru/gtk-4.0"
            theme_dir.mkdir(parents=True)
            (theme_dir / "gtk.css").touch()
            settings, values = gtk_settings()
            with (patch.object(ThemeManager, "_desktop_settings", return_value=None),
                  patch.object(Gtk.Settings, "get_default", return_value=settings),
                  patch("theme.preference_file", return_value=preference),
                  patch.object(GLib, "get_system_data_dirs", return_value=[temp])):
                manager = ThemeManager(lambda *_: None)
                try:
                    self.assertTrue(manager.dark)
                    manager.set_preference("light")
                    self.assertEqual(values["gtk-theme-name"], "Yaru")
                    manager.set_preference("system")
                    self.assertTrue(manager.dark)
                    self.assertEqual(values["gtk-theme-name"], "Yaru-dark")
                finally:
                    manager.close()
                self.assertEqual(values["gtk-theme-name"], "Yaru-dark")


if __name__ == "__main__":
    unittest.main()
