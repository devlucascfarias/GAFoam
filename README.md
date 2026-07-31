# GAFoam

Desktop front-end for [OpenFOAM](https://www.openfoam.com/) built with Python and PySide6 (Qt 6). It wraps case editing, mesh generation, solver execution and residual monitoring into a single window, driving the standard OpenFOAM command-line utilities through `QProcess` rather than reimplementing them.

The application does not link against OpenFOAM libraries. It requires a sourced OpenFOAM environment in the shell that launches it, so that `blockMesh`, `snappyHexMesh`, the solvers and `$WM_PROJECT_DIR` resolve on `PATH`.

## Feature Overview

### Case management
- Case directories are opened through a dialog that validates the mandatory OpenFOAM layout (`0/`, `constant/`, `system/`). A directory missing any of the three is rejected.
- A `QFileSystemModel` tree is rooted at the case directory. Single click opens a file in a tab; `.stl` and `.obj` files are routed to the 3D viewer instead of the text editor.
- Opening a case populates the `controlDict` dock and the convergence monitor. The geometry scan is deferred until the 3D panel is actually opened, so no mesh is loaded for a session that only edits dictionaries.

### Dictionary editor
- `CodeEditor` (`QPlainTextEdit` subclass) with a line-number gutter, current-line highlight and Ctrl+wheel zoom.
- `SimpleHighlighter` covers OpenFOAM dictionary syntax and additionally colours C++ code embedded in `#{ ... #}` blocks, using range exclusion so the inner and outer grammars do not overlap.
- `FindReplaceBar` (Ctrl+F, Esc to dismiss) with case-sensitive and whole-word flags, find next/previous, replace and replace-all.
- A live linter (`gafoam.foamlint`) runs on a debounce timer and reports the first structural problem found: unbalanced `{}`, `[]`, `()` with the offending line number, or an entry that appears to be missing its terminating semicolon.

  The linter first neutralises everything that is not dictionary code — line comments, multi-line `/* */` blocks, quoted strings and embedded `#{ ... #}` C++ — while preserving line numbering. Braces inside a commented-out block therefore do not unbalance the file, and the standard OpenFOAM banner (whose `=========` and `\\ / F ield |` lines are not valid entries) no longer produces a spurious "missing semicolon" on line 2. The semicolon check is also suppressed inside `( ... )` lists, where values are space-separated, and for `#include`/`$macro` directives, sub-dictionary headers and `nonuniform List<...>` fields whose element count sits on the following line.

### Geometry viewer
- The 3D panel is on demand: it is not part of the editor tab strip at startup, and becomes a tab the first time a mesh file is opened. Closing that tab keeps the panel alive for reuse; reopening it does not rescan a case already scanned.
- `CaseGeometryWidget` walks the case tree and collects every `.stl` and `.obj`, skipping `platforms`, `processor*`, `venv`, `.venv` and cache directories. Clicking a mesh in the file tree selects that surface in the panel; a mesh outside the scan is loaded on its own.
- Meshes render through PyVista (`pyvistaqt.QtInteractor`). Each surface gets a checkable list entry for per-mesh visibility.
- Per-mesh point/cell counts and X/Y/Z bounds, representation modes (surface, wireframe, points), opacity control, axis-aligned camera presets and screenshot export.

### Execution
All commands run with the working directory set to the case root. A single `QProcess` is used, so a second command is refused while one is active.

| Control | Command |
| --- | --- |
| Run (Ctrl+R) | `/bin/bash -lc ./Allrun` |
| Stop | SIGTERM to the whole process tree, SIGKILL after 2.5 s |
| blockMesh | `blockMesh` |
| checkMesh | `checkMesh` |
| snappyHexMesh | `snappyHexMesh` |
| Utilities > decomposePar | `decomposePar` |
| Utilities > reconstructPar | `reconstructPar` |
| Utilities > yPlus | `yPlus` |
| Utilities > Clean case | `./Allclean` if present, otherwise `foamCleanTutorials` |

If `Allrun` is absent, a default one is generated (clean `processor*`, `decomposePar`, source `RunFunctions`, `runParallel $(getApplication)`) and the executable bit is set when missing.

Because `Allrun` typically backgrounds the solver via `runParallel`, the script exits long before the simulation does. On exit with log-following enabled the UI switches to a `Running (bg)` state and keeps tailing the log; Stop then resolves the still-running solver processes by scanning for processes whose working directory is the case, rather than by the (already dead) script PID.

### Log following and residual parsing
A `QTimer` polls at 600 ms. The target log is `log.foam` when present, otherwise the most recently modified `log.*` in the case root, excluding `*.log`. The reader tracks byte offset and inode so that log rotation or recreation is detected and the tail restarts cleanly.

Each polled chunk is scanned for:

- `Time = <t>` — current simulation time, used as the time axis.
- `Solving for <field>, Initial residual = <r>` — per-field initial residuals. `Ux`, `Uy` and `Uz` are collapsed into a single `|U|` magnitude curve, so 2D and 3D cases plot identically.
- `y+ : min = ..., max = ..., average = ...`
- `Courant Number mean: ... max: ...`
- `deltaT = ...`
- `minMag()/maxMag() of U` and `min()/max() of p` from `volFieldValue` function objects.
- A custom flow-rate function object line of the form `Time: ... | Area: ... | Q: ... | U_mean: ...`.

### Residual plot
`ResidualsWidget` uses `PySide6.QtCharts` (it degrades to a placeholder label if the QtCharts module is unavailable). Linear or logarithmic Y scale, X axis switchable between physical time and iteration count, and series filtering by group (all, velocities, pressure, turbulence). Series are limited to a 200-point rolling window for real-time performance, with animations disabled. Legend markers toggle individual curves; scroll wheel zooms, right click resets zoom, drag rubber-bands a region. The plot is hidden by default and only splits the editor area horizontally while a solver run is active.

### Convergence monitor
A side table in the Simulation tab parses the `residualControl` block of `system/fvSolution` by brace matching and shows, per variable, the latest residual against its tolerance. Matching follows OpenFOAM's own semantics: a literal key wins over a pattern, and patterns must match the whole field name, so a `p` entry cannot capture `epsilon` or `p_rgh`. The default target is `1e-5` when no entry matches. Values at or below target render green, otherwise red.

### controlDict dock
A dockable panel reads `application`, `endTime`, `deltaT` and `writeInterval` from `system/controlDict` with comments stripped, exposes the three numeric values as spin boxes, and writes them back in place without rewriting the rest of the dictionary. Toggled from the View menu.

### Embedded terminal
`TerminalWidget` runs an interactive `/bin/bash -i` with a coloured `PS1`, translates ANSI SGR escape sequences to HTML for display, and forwards single-line input. It exposes `append()` so code written against a plain log view keeps working.

## Repository Layout

The code lives in a `src/` layout: `main.py` is a launcher, everything else is
the `gafoam` package.

```
main.py                  Launcher: puts src/ on sys.path and calls gafoam.app.run().
pyproject.toml           Package metadata and pytest configuration.
requirements.txt         Runtime dependencies.
src/gafoam/
  app.py                 run(): QApplication + MainWindow + event loop.
  main_window.py         MainWindow: layout, QProcess handling, log polling.
  panels.py              ConvergenceMonitorWidget, ControlDictDockWidget.
  editor.py              CodeEditor, SimpleHighlighter, FindReplaceBar,
                         EditorContainerWidget (editor + find bar + linter).
  residuals.py           ResidualsWidget and InteractiveChartView (QtCharts).
  stl_viewer.py          STLViewer (PyVista render surface), CaseGeometryWidget.
  filebrowser.py         QFileSystemModel-backed case tree.
  menus.py               Menu bar construction.
  handlers.py            stdout/stderr/finished callbacks for the QProcess.
  terminal.py            Embedded bash terminal with ANSI-to-HTML rendering.
  logparse.py            Solver-log parsing and log-file selection. No Qt.
  foamdict.py            controlDict / fvSolution reading and writing. No Qt.
  foamlint.py            Dictionary syntax checking. No Qt.
  resources.py           Packaged asset lookup (icon_path).
  icons/                 SVG toolbar icons.
  modules/               Plugin scaffold (abstract Module base, mesh module).
                         Not wired into MainWindow yet.
tests/                   pytest suite.
```

The four Qt-free modules (`logparse`, `foamdict`, `foamlint`, `resources`) hold
the logic that used to sit inside widget methods. Widgets delegate to them, which
keeps parsing and validation testable without a display.

## Requirements

- Python 3.12 or newer
- A working OpenFOAM installation, with its environment sourced before launch
- Linux (process control relies on `ps`, POSIX signals and `/proc`)

Python packages:

```bash
pip install -r requirements.txt
```

`PySide6.QtCharts` ships with the standard PySide6 wheel. On some distribution-packaged builds it is a separate package; without it the residual plot falls back to a placeholder while the rest of the application still runs.

## Running

```bash
source /opt/openfoam*/etc/bashrc   # or your installation's equivalent
python3 main.py
```

No installation step is needed: `main.py` adds `src/` to the import path. To
install the package instead — which also provides a `gafoam` console script —
run `pip install -e .`.

Launching from a shell without the OpenFOAM environment leaves the toolbar functional but every command fails with a "no such file" error in the console.

## Tests

```bash
pip install pytest
python -m pytest
```

`pyproject.toml` points pytest at `src/` and `tests/`, so no path setup is
needed. The suite covers log parsing, log-file selection, dictionary read/write,
`residualControl` matching, the linter (including the OpenFOAM banner and
multi-line lists), package imports and asset presence.

Interface tests run with `QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`.
They replace `CaseGeometryWidget` with a stub, because `pyvistaqt.QtInteractor`
needs a real X server and aborts the process in a headless environment. Rendering
itself is therefore not covered by the automated suite.

## Typical Workflow

1. Open Case and select the case root. The layout is validated and the `controlDict` and convergence panels populate.
2. Edit dictionaries in the tabbed editor. The linter flags brace and semicolon problems as you type; Ctrl+S saves.
3. Adjust `endTime`, `deltaT` and `writeInterval` from the controlDict dock when a full edit is unnecessary.
4. Click any `.stl` in the file tree to open the 3D panel and inspect the geometry.
5. Generate the mesh with blockMesh, then snappyHexMesh; inspect quality with checkMesh. Output goes to the Console tab.
6. Run (Ctrl+R). The view switches to the Simulation tab, the residual plot appears, and the solver log is tailed with the convergence table updating per field.
7. Stop terminates the solver and all descendants, including runs that outlived the `Allrun` script.

## Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| Ctrl+R | Run simulation (`Allrun`) |
| Ctrl+S | Save current file |
| Ctrl+Shift+S | Save as |
| Ctrl+F | Find and replace bar |
| Esc | Close find bar |
| Ctrl+0 | Reset UI scale |
| Ctrl+wheel | Zoom editor font |

## Known Constraints

- Linux only. Process-tree termination uses `ps --ppid` and POSIX signals.
- One command at a time; the shared `QProcess` rejects concurrent launches.
- The UI is in Portuguese while code identifiers are in English.
- The `modules/` plugin system defines its interface but is not loaded by `MainWindow`.
- Residual parsing targets OpenFOAM's standard log format. Solvers with non-standard output produce no curves.
