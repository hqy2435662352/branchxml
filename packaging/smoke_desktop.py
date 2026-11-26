"""Exercise the installed desktop entry and GTK shortcuts in a private Sway session."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from xml.etree.ElementTree import fromstring

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, Gtk

APP_ID = "io.github.hqy2435662352.BranchXML"


def wait_for(condition, description):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        result = condition()
        if result:
            return result
        time.sleep(.05)
    raise AssertionError(description)


def find_window(title):
    tree = json.loads(subprocess.check_output(["swaymsg", "-t", "get_tree", "-r"]))
    pending = [tree]
    while pending:
        node = pending.pop()
        if node.get("app_id") == APP_ID and title in (node.get("name") or ""):
            return node
        pending.extend(node.get("nodes", []) + node.get("floating_nodes", []))


def sequence(*steps):
    # One virtual device and one keymap, as on a physical keyboard.
    keys = ["wtype"]
    for step in steps:
        keys.extend(["-s", "120", *step])
    subprocess.run(keys, check=True)


def ctrl(key):
    return ("-M", "ctrl", "-k", key, "-m", "ctrl")


def main():
    Gtk.init()
    app = (Gio.DesktopAppInfo.new_from_filename(sys.argv[1]) if len(sys.argv) > 1
           else Gio.DesktopAppInfo.new(APP_ID + ".desktop"))
    assert app is not None and app.get_icon().get_names()[0] == APP_ID
    theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
    assert theme.has_icon(APP_ID), "Installed icon is missing"
    environment = Gdk.Display.get_default().get_app_launch_context()

    def launch(path):
        assert app.launch([Gio.File.new_for_path(str(path))], environment)
        window = wait_for(lambda: find_window(path.name), "The launcher did not open the selected file")
        subprocess.run(["swaymsg", "-q", f"[con_id={window['id']}] focus"], check=True)
        time.sleep(.25)
        return window

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "导航 recipe.xml"
        original = ("\ufeff<r xmlns:p='urn:origin'>\r\n<summary>终点 LM2</summary>"
                    "<param key='target_id' value='LM2'/><p:sample id='7'/>\r\n</r>").encode()
        path.write_bytes(original)
        first = launch(path)
        sequence(ctrl("f"), ("LM2",), ("-k", "F3"), ("-k", "Escape"), ("-k", "F2"),
                 ("LM3",), ("-k", "Tab"), ctrl("s"))
        expected = original.replace(b"value='LM2'", b"value='LM3'")
        wait_for(lambda: path.read_bytes() == expected, "Changing the located value did not produce an exact one-field save")
        sequence(ctrl("z"), ctrl("s"))
        wait_for(lambda: path.read_bytes() == original, "Undo and save did not restore the original bytes")
        sequence(ctrl("f"), ("p:sample",), ("-k", "Escape"), ctrl("c"))

        other = Path(tmp) / "second.xml"
        other.write_text("<r xmlns:p='urn:other'><holder/></r>")
        launch(other)
        sequence(ctrl("f"), ("holder",), ("-k", "Escape"), ctrl("v"), ctrl("s"))
        wait_for(lambda: fromstring(other.read_bytes()).find("holder/{urn:origin}sample") is not None,
                 "Pasting between windows did not preserve the subtree namespace")
        sequence(ctrl("w"))
        wait_for(lambda: not find_window(other.name), "The saved document did not close")
        subprocess.run(["swaymsg", "-q", f"[con_id={first['id']}] focus"], check=True)
        sequence(ctrl("w"))
        wait_for(lambda: not find_window(path.name), "The first document did not close")
        print("Desktop activation, icon lookup, keyboard search/edit, exact undo and cross-window clipboard passed.")


if __name__ == "__main__":
    # Keep the Wayland seat's keyboard capability alive between wtype invocations.
    keyboard = subprocess.Popen(["wtype", "-s", "600000", "-k", "space"])
    try:
        wait_for(lambda: any(device["type"] == "keyboard" for device in
                             json.loads(subprocess.check_output(["swaymsg", "-t", "get_inputs", "-r"]))),
                 "The test compositor has no keyboard")
        main()
    finally:
        keyboard.terminate()
        keyboard.wait()
