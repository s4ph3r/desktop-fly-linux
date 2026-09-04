// linuxX11.js — the Linux half of Environment.swift, mirroring win32.js.
//
// macOS reads window terrain with CGWindowListCopyWindowInfo and mouse state
// via NSEvent global monitors. Windows does the same via user32/dwmapi through
// koffi. Neither exists on X11, so this module shells out to a small Python
// script (linux_env.py) that talks directly to the X server through python-xlib:
//
//   window terrain        -> XQueryTree (root) + XGetGeometry + _NET_WM_WINDOW_TYPE
//   mouse buttons         -> XQueryPointer on the root window
//
// Everything here is poll-only and permission-free: it reads window geometry
// and whether a mouse button went down — never keystrokes, never window
// contents. Keyboard activity is inferred in main.js from the system idle
// timer, so no key is ever polled individually.
//
// The Python script is invoked synchronously via spawnSync (main.js calls these
// functions on every frame) and its JSON output is parsed. This avoids the
// fragility of a native C addon (which crashed under Muffin's X11 server).

import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PYTHON_SCRIPT = join(__dirname, 'linux_env.py');

let pythonAvailable = null;

function checkPython() {
  if (pythonAvailable !== null) return pythonAvailable;
  try {
    const r = spawnSync('python3', ['--version'], { stdio: 'ignore' });
    pythonAvailable = r.status === 0;
  } catch {
    pythonAvailable = false;
  }
  return pythonAvailable;
}

function runPython(args, timeoutMs = 5000) {
  const result = spawnSync('python3', [PYTHON_SCRIPT, ...args], {
    encoding: 'utf8',
    timeout: timeoutMs,
  });
  if (result.status !== 0 || !result.stdout) return null;
  try {
    return JSON.parse(result.stdout.trim());
  } catch {
    return null;
  }
}

export function linuxAvailable() { return checkPython(); }

// Alt-tab-visible top-level windows with their on-screen frames, in physical
// pixels. Mirrors the CGWindowList filter: normal application layer, not our
// own process, visible, at least 160x60. Tool/dock/desktop windows are skipped.
export function listWindows(ownPid) {
  if (!checkPython()) return [];
  const parsed = runPython([String(ownPid), 'windows']);
  if (!parsed || !parsed.windows) return [];
  return parsed.windows.map((w) => ({
    id: w.id, left: w.left, top: w.top, right: w.right, bottom: w.bottom,
  }));
}

// Mouse-button state since the previous call. Mirrors win32.js's
// pollMouseButtons() which returns a boolean pair.
export function pollMouseButtons() {
  if (!checkPython()) return { left: false, right: false };
  const parsed = runPython([String(0), 'mouse']);
  if (!parsed || typeof parsed.left === 'undefined') {
    return { left: false, right: false };
  }
  return { left: !!parsed.left, right: !!parsed.right };
}
