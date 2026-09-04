#!/usr/bin/env python3
"""linux_env.py — the Linux half of Environment.swift, mirroring win32.js.

macOS reads window terrain with CGWindowListCopyWindowInfo and mouse state via
NSEvent global monitors. Windows does the same via user32/dwmapi through koffi.
Neither exists on X11, so this script talks directly to the X server through
python-xlib:

    window terrain        -> XQueryTree (root) + XGetGeometry + _NET_WM_WINDOW_TYPE
    mouse buttons         -> XQueryPointer on the root window

Everything here is poll-only and permission-free: it reads window geometry and
whether a mouse button went down — never keystrokes, never window contents.
Keyboard activity is inferred in main.js from the system idle timer, so no key
is ever polled individually.

Usage:
    python3 linux_env.py <own_pid> [mode]

  mode "windows" (default): print JSON {"windows":[{"id",left,top,right,bottom},...]}
  mode "mouse":              print JSON {"left":bool,"right":bool}

Each window is wrapped in try/except so a window that dies mid-enumeration or
has unreadable properties simply gets skipped — no crash, unlike the previous
C addon.
"""

import sys
import json
import struct


def _init_atoms(disp):
    """Intern the atoms we need once per display connection."""
    return {
        "window_type": disp.intern_atom("_NET_WM_WINDOW_TYPE"),
        "wm_class": disp.intern_atom("_NET_WM_CLASS"),
        "wm_pid": disp.intern_atom("_NET_WM_PID"),
        "toolbar": disp.intern_atom("_NET_WM_WINDOW_TYPE_TOOLBAR"),
        "dock": disp.intern_atom("_NET_WM_WINDOW_TYPE_DOCK"),
        "desktop": disp.intern_atom("_NET_WM_WINDOW_TYPE_DESKTOP"),
        "menu": disp.intern_atom("_NET_WM_WINDOW_TYPE_MENU"),
        "bar": disp.intern_atom("_NET_WM_WINDOW_TYPE_BAR"),
        "notification": disp.intern_atom("_NET_WM_WINDOW_TYPE_NOTIFICATION"),
        "splash": disp.intern_atom("_NET_WM_WINDOW_TYPE_SPLASH"),
        "dialog": disp.intern_atom("_NET_WM_WINDOW_TYPE_DIALOG"),
    }


def _get_prop(window, atom):
    """Return the raw property bytes for a window/atom, or None if absent."""
    try:
        return window.get_property(atom, 0, 0, 65536)
    except Exception:
        return None


def _window_type_atom(window, atoms):
    """Return the _NET_WM_WINDOW_TYPE atom value for a window, or None."""
    prop = _get_prop(window, atoms["window_type"])
    if not prop or len(prop) < 4:
        return None
    # Atom is stored as an unsigned long (host byte order).
    return struct.unpack("<I", prop[:4])[0]


def _wm_pid(window, atoms):
    """Return the _NET_WM_PID for a window, or None."""
    prop = _get_prop(window, atoms["wm_pid"])
    if not prop or len(prop) < 4:
        return None
    return struct.unpack("<I", prop[:4])[0]


def list_windows(own_pid):
    """Alt-tab-visible top-level windows with on-screen frames, in physical pixels.

    Mirrors the CGWindowList filter: normal application layer, not our own
    process, visible, at least 160x60. Tool/dock/desktop windows are skipped.
    """
    from Xlib.display import Display
    from Xlib import X

    disp = Display()
    atoms = _init_atoms(disp)
    root = disp.screen().root

    # Query the root's children directly — always yields top-level windows.
    try:
        children = root.query_tree()
    except Exception:
        disp.close()
        return []
    child_list = children.children or []

    result = []
    for child in child_list:
        try:
            attrs = child.get_attributes()
            if not attrs or attrs.map_state != X.IsViewable:
                continue  # skip hidden/iconified windows

            geom = child.get_geometry()
            width, height = geom.width, geom.height
            if width < 160 or height < 60:
                continue  # mirror the Win32 size filter

            # Skip non-application window types (toolbars, docks, desktop, etc.).
            wt = _window_type_atom(child, atoms)
            if wt is not None and wt in (
                atoms["toolbar"], atoms["dock"], atoms["desktop"], atoms["menu"],
                atoms["bar"], atoms["notification"], atoms["splash"], atoms["dialog"],
            ):
                continue

            # Skip our own overlay / brain windows.
            pid = _wm_pid(child, atoms)
            if pid is not None and pid == own_pid:
                continue

            result.append({
                "id": int(child.id),
                "left": geom.x,
                "top": geom.y,
                "right": geom.x + width,
                "bottom": geom.y + height,
            })
        except Exception:
            # A window can die mid-enumeration; just skip it.
            continue

    disp.close()
    return result


def poll_mouse_buttons():
    """Mouse-button state since the previous call via XQueryPointer."""
    from Xlib.display import Display
    from Xlib import X

    disp = Display()
    root = disp.screen().root
    try:
        q = root.query_pointer()
        state = q.mask
        return {
            "left": bool(state & X.Button1Mask),
            "right": bool(state & X.Button3Mask),
        }
    finally:
        disp.close()


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing pid"}))
        return

    try:
        own_pid = int(sys.argv[1])
    except ValueError:
        own_pid = 0

    mode = sys.argv[2] if len(sys.argv) > 2 else "windows"

    if mode == "mouse":
        print(json.dumps(poll_mouse_buttons()))
    else:
        print(json.dumps({"windows": list_windows(own_pid)}))


if __name__ == "__main__":
    main()
