# GAFoam

Desktop front-end for [OpenFOAM](https://www.openfoam.com/) built with Python and PySide6 (Qt 6). It wraps case editing, mesh generation, solver execution and residual monitoring into a single window, driving the standard OpenFOAM command-line utilities through `QProcess` rather than reimplementing them.

The application does not link against OpenFOAM libraries. It requires a sourced OpenFOAM environment in the shell that launches it, so that `blockMesh`, `snappyHexMesh`, the solvers and `$WM_PROJECT_DIR` resolve on `PATH`.

## Feature Overview

### Case management
- Case directories are opened through a dialog that validates the mandatory OpenFOAM layout (`0/`, `constant/`, `system/`). A directory missing any of the three is rejected.
- A `QFileSystemModel` tree is rooted at the case directory. Single click opens a file in a tab; `.stl` files are routed to the 3D viewer instead of the text editor.
- Opening a case propagates to the geometry scanner, the `controlDict` dock and the convergence monitor in one pass.

### Dictionary editor
- `CodeEditor` (`QPlainTextEdit` subclass) with a line-number gutter, current-line highlight and Ctrl+wheel zoom.
- `SimpleHighlighter` covers OpenFOAM dictionary syntax and additionally colours C++ code embedded in `#{ ... #}` blocks, using range exclusion so the inner and outer grammars do not overlap.
- `FindReplaceBar` (Ctrl+F, Esc to dismiss) with case-sensitive and whole-word flags, find next/previous, replace and replace-all.
- A live linter runs on a debounce timer and reports the first structural error found: unbalanced `{}`, `[]`, `()` with the offending line number, and statements that appear to be missing a terminating semicolon. Sub-dictionary openings are excluded from the semicolon check by lookahead.

### Geometry viewer
- `CaseGeometryWidget` walks the case tree and collects every `.stl` and `.obj`, skipping `platforms`, `processor*`, `venv`, `.venv` and cache directories.
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
A side table in the Simulation tab parses the `residualControl` block of `system/fvSolution` by brace matching and shows, per variable, the latest residual against its tolerance. Field names in `residualControl` are treated as regular expressions (matching OpenFOAM's own semantics) with a literal-substring fallback; the default target is `1e-5` when no entry matches. Values at or below target render green, otherwise red.

### controlDict dock
A dockable panel reads `application`, `endTime`, `deltaT` and `writeInterval` from `system/controlDict` with comments stripped, exposes the three numeric values as spin boxes, and writes them back in place without rewriting the rest of the dictionary. Toggled from the View menu.

### Embedded terminal
`TerminalWidget` runs an interactive `/bin/bash -i` with a coloured `PS1`, translates ANSI SGR escape sequences to HTML for display, and forwards single-line input. It exposes `append()` so code written against a plain log view keeps working.

## Repository Layout

```
main.py            Entry point; creates QApplication and MainWindow.
main_window.py     MainWindow, process management, log polling, residual
                   parsing, ConvergenceMonitorWidget, ControlDictDockWidget.
editor.py          CodeEditor, SimpleHighlighter, FindReplaceBar,
                   EditorContainerWidget (editor + find bar + linter).
residuals.py       ResidualsWidget and InteractiveChartView (QtCharts).
stl_viewer.py      STLViewer (PyVista render surface) and CaseGeometryWidget.
filebrowser.py     QFileSystemModel-backed case tree.
menus.py           Menu bar construction.
handlers.py        stdout/stderr/finished callbacks for the QProcess.
terminal.py        Embedded bash terminal with ANSI-to-HTML rendering.
modules/           Plugin scaffold (abstract Module base, mesh module).
                   Not wired into MainWindow yet.
icons/             SVG toolbar icons.
```

## Requirements

- Python 3.12 or newer
- A working OpenFOAM installation, with its environment sourced before launch
- Linux (process control relies on `ps`, POSIX signals and `/proc`)

Python packages:

```bash
pip install PySide6 pyvista pyvistaqt numpy vtk
```

`PySide6.QtCharts` ships with the standard PySide6 wheel. On some distribution-packaged builds it is a separate package; without it the residual plot falls back to a placeholder while the rest of the application still runs.

## Running

```bash
source /opt/openfoam*/etc/bashrc   # or your installation's equivalent
python3 main.py
```

Launching from a shell without the OpenFOAM environment leaves the toolbar functional but every command fails with a "no such file" error in the console.

## Typical Workflow

1. Open Case and select the case root. The layout is validated and the geometry, `controlDict` and convergence panels populate.
2. Edit dictionaries in the tabbed editor. The linter flags brace and semicolon problems as you type; Ctrl+S saves.
3. Adjust `endTime`, `deltaT` and `writeInterval` from the controlDict dock when a full edit is unnecessary.
4. Generate the mesh with blockMesh, then snappyHexMesh; inspect quality with checkMesh. Output goes to the Console tab.
5. Run (Ctrl+R). The view switches to the Simulation tab, the residual plot appears, and the solver log is tailed with the convergence table updating per field.
6. Stop terminates the solver and all descendants, including runs that outlived the `Allrun` script.

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
- The UI is in Portuguese while code identifiers are in English, per the convention in `CODE_GUIDE.md`.
- The `modules/` plugin system defines its interface but is not loaded by `MainWindow`.
- Residual parsing targets OpenFOAM's standard log format. Solvers with non-standard output produce no curves.
