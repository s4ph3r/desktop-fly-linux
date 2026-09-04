# DesktopFly for Windows

The Windows port of DesktopFly: the same 3D fruit fly on a transparent
desktop overlay, driven by the same 1 kHz leaky-integrate-and-fire simulation
of 668 real neurons from the FlyWire connectome (FAFB v783).

The brain is a line-by-line port of `Sim.swift`; the body and behavior are a
line-by-line port of `FlyModel.swift`. Both test suites came across with them
and are the ground truth here just as they are on macOS.

## Why a port and not a rebuild

macOS DesktopFly links `Cocoa` and `SceneKit`, neither of which exists on
Windows — the open-source Swift toolchain ships only stdlib, Foundation,
Dispatch and WinSDK. Everything that draws or touches the system had to be
rewritten; everything that computes came over unchanged in behavior.

| macOS | Windows | Linux/X11 |
|---|---|---|
| SceneKit | three.js (WebGL) | three.js (WebGL) |
| AppKit `NSPanel`, borderless + `ignoresMouseEvents` | Electron `BrowserWindow`, `transparent` + `setIgnoreMouseEvents` | same as Windows |
| `NSStatusItem` menu bar | `Tray` | same as Windows |
| `CGWindowListCopyWindowInfo` | `EnumWindows` + `DwmGetWindowAttribute` via koffi | X11 via Python + python-xlib (`linux_env.py`) |
| `NSEvent` global mouse monitor | `GetAsyncKeyState(VK_LBUTTON/VK_RBUTTON)` | `XQueryPointer` on the root window (via Python) |
| `CGEventSource` idle | `powerMonitor.getSystemIdleTime()` | same as Windows |
| `ProcessInfo.thermalState` | CPU load (no Windows equivalent without vendor drivers) | same — CPU-load tempo |
| one `NSScreen`, hop via menu | one overlay across the whole virtual desktop | same as Windows |

## Run

```sh
npm install
npm start              # tray icon; quit from there
npm run simtest        # circuit invariants (MUST pass after sim changes)
npm run behaviortest   # 18 end-to-end sim -> body checks
npm test               # both
```

`DESKTOPFLY_DEBUG=1 npm start` logs window terrain, overlay geometry and
renderer console output to stderr.

### Linux / X11

The Electron port runs on Linux out of the box — three.js draws headlessly, so
the fly's body needs no GPU. The only platform-specific change is how it senses
the desktop: macOS uses `CGWindowListCopyWindowInfo` and Windows uses user32 via
koffi, but neither exists under X11. Instead this port shells out to a small
Python script (`src/linux_env.py`) that talks directly to the X server through
[python-xlib](https://pypi.org/project/python-Xlib/):

- **Window terrain** — `XQueryTree` on the root window, then for each child
  `get_attributes()` (visible), `get_geometry()` (frame) and `_NET_WM_WINDOW_TYPE`
  (skip toolbars/docks/desktop). Own-process windows are filtered out by
  `_NET_WM_PID`. Each window is wrapped in try/except, so a window that dies
  mid-enumeration is skipped rather than crashing the app.
- **Mouse buttons** — `XQueryPointer` on the root window → `Button1Mask` /
  `Button3Mask`.

The Python script is invoked synchronously from `src/linuxX11.js` via
`spawnSync`, so the interface (`listWindows`, `pollMouseButtons`,
`linuxAvailable`) matches `win32.js` exactly. On a machine without python3 or
python-xlib the fly still runs but loses window ledges and click taps (a warning
is printed on startup).

```sh
pip install python-Xlib        # or: sudo apt install python3-Xlib
npm start -- --disable-gpu     # see "GPU note" below
```

`--disable-gpu` is recommended under X11 — Electron v32's GPU process can crash
on launch in some drivers (see [Known limits](#known-limits)). It only affects
the compositor; the fly itself renders through three.js.

The suites run on bare Node — three.js builds the fly's scene graph headlessly,
so behavior is testable without a GPU.

## What the fly senses

Everything is poll-only and needs no permission dialog. As on macOS, the fly
learns *when* things happen, never *what*:

- **Cursor** — position and velocity become a looming stimulus, split between
  the two eyes by bearing, fed to 314 LC4/LPLC2 neurons. A lunge drives the
  DNp01 giant fiber and the fly takes off ~4 ms later. Fast motion nearby is
  an air puff on the sensory pathway.
- **Clicks** — a global mouse-button press is a tap on the fly's substrate,
  stimulating sensory neurons with a strength that falls off with distance.
- **Windows** — top edges of real windows are walkable ledges; a window
  appearing near the fly is a looming object. Only geometry is read: the
  pixels underneath the fly are never sampled.
- **Typing** — the system idle timer says an input device was touched; if the
  cursor did not move and no button went down, that was the keyboard. No key
  is ever polled individually.
- **Clock and CPU load** — circadian activity curve and an ectotherm's tempo.

## Multi-monitor

The overlay spans the union of all displays, so walking and flying between
monitors is ordinary movement rather than a mode switch. Displays are passed
into the scene as rects, so the fly never targets the dead corners of a
non-rectangular layout. "Send Fly to Next Display" in the tray menu nudges it
across on demand.

Windows clamps a fixed-size window to one monitor's work area, which would
leave the scene believing it is wider than the window really is — the fly then
walks into coordinates that are not on screen and appears to vanish. The
overlay therefore stays resizable and the scene is always told the window's
*actual* bounds.

## Known limits

- Windows does not composite overlays above **exclusive**-fullscreen apps; the
  fly is hidden there. Borderless fullscreen is fine.
- `koffi` provides the Win32 calls. Without it the fly still runs, but loses
  window ledges and click taps (a warning is printed on startup).
- On Linux/X11, Electron v32's GPU process can fail to launch under some drivers
  (`GPU process isn't usable`, sometimes a crash). Start with `npm start --
  --disable-gpu` — the fly renders through three.js regardless.
- The old Windows port used `screen.screenToDipPoint`, which Electron v32
  removed; the Linux path converts physical pixels to DIP via the display's
  `scaleFactor` instead.

## Layout

| file | contents |
|---|---|
| `main.js` | Electron main: overlay + brain windows, tray, environment senses |
| `preload.mjs` | the only main↔renderer bridge |
| `renderer/overlay.js` | `buildScene` + `Coordinator` from `main.swift` |
| `renderer/brain.js` | port of `BrainView.swift` |
| `src/sim.js` | port of `Sim.swift` (`LIFSim`, `SpikeBus`, `BrainSignals`) |
| `src/flymodel.js` | port of `FlyModel.swift` (body geometry + behavior) |
| `src/signals.js` | port of `SignalBuilder` |
| `src/win32.js` | user32/dwmapi through koffi |
| `src/linux_env.py` | X11 window/mouse sensing via python-xlib (shelled out from linuxX11.js) |
| `src/linuxX11.js` | Linux environment bridge — runs linux_env.py synchronously |
| `src/environment.js` | circadian curve, CPU-load tempo |
| `src/data.js` | Node-only JSON loading (kept out of `sim.js` for the renderer) |
| `test/` | ports of `--simtest` and `--behaviortest` |

Data comes from `../data/` — the same shipped `brain_points.json` and
`circuit.json`, under the same CC BY-NC 4.0 terms.
