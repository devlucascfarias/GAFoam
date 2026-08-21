# GAFoam — OpenFOAM Desktop GUI

**GAFoam** is a desktop graphical user interface for [OpenFOAM](https://www.openfoam.com/) built with Python and PySide6 (Qt 6). Designed with the **IBM Carbon Design System (g10)**, it integrates 3D geometry inspection, boundary condition editing, case dictionary management, numerical scheme configuration, solver execution, live residual monitoring, and automated PDF report generation into a unified, responsive interface.

---

## Feature Overview

### Modern IBM Carbon UI Design
- Implementation of the **IBM Carbon Design System (g10)** with clean borders, flat palettes, and high-contrast styling.
- Bundled typefaces: **Inter** for UI controls and **Fira Code** for monospace code editors and logs.
- Responsive toolbar with SVG vector icons.

### 3D Geometry & Mesh Viewer (Geometry Tab)
- Powered by **PyVista** (`pyvistaqt.QtInteractor`) for 3D rendering of surface meshes (`.stl`, `.obj`).
- **Watertight & Quality Diagnostics**:
  - Automatic detection of closed/watertight geometry (SnappyHexMesh-ready validation).
  - Open boundary edges counter, surface area ($m^2$), enclosed volume ($m^3$), and bounding box ($\Delta X, \Delta Y, \Delta Z$) calculations.
- **Interactive Clipping & Slicing Planes**:
  - Dynamic slicing along X, Y, or Z normals with position slider and normal inverter.
- **3D Point-to-Point Ruler & Measurement**:
  - Click-to-measure tool calculating Euclidean distance and coordinate deltas ($\Delta X, \Delta Y, \Delta Z$).
- **Rendering Controls**:
  - Multiple representation modes: Clean Surface, Surface + Edges, Wireframe, and Point Cloud.
  - Opacity slider, background color switch (Dark / Light / Gradient), and axis-aligned camera presets (+X, -X, +Y, -Y, +Z, -Z, Isometric).
  - High-resolution screenshot PNG export.

### Visual Boundary Condition Editor (0/ Directory)
- Visual inspector and editor for field files in the `0/` directory (`p`, `U`, `k`, `omega`, `epsilon`, `nut`, `alphat`, etc.).
- Dropdown selector with standard OpenFOAM boundary condition types:
  - `fixedValue`, `zeroGradient`, `noSlip`, `calculated`, `inletOutlet`, `pressureInletOutletVelocity`, `totalPressure`, `symmetryPlane`, `slip`, `empty`, `wedge`, `cyclic`, `kqRWallFunction`, `nutUSpaldingWallFunction`, `omegaWallFunction`, `epsilonWallFunction`, etc.
- In-place editing of patch values with synchronized disk write and editor reload.

### Unified Case Settings Dock
Dockable panel with 5 collapsible sections for rapid case configuration:
1. **Time & Run Controls** (`system/controlDict`):
   - `application`, `startFrom`, `startTime`, `stopAt`, `endTime`, `deltaT`, `writeControl`, `writeInterval`, `purgeWrite`, `adjustTimeStep`, `maxCo`.
2. **Parallel Execution** (`system/decomposeParDict`):
   - `numberOfSubdomains` with auto-detect CPU cores button.
   - Decomposition method selector (`scotch`, `hierarchical`, `simple`, `kahip`).
3. **Turbulence & Physics** (`constant/turbulenceProperties` or `momentumTransport`):
   - Simulation type: `RAS` (RANS), `LES`, or `laminar`.
   - Model selector: `kOmegaSST`, `kEpsilon`, `SpalartAllmaras`, `realizableKE`, `rngKE`, `WALE`, `Smagorinsky`.
   - Turbulence calculation toggle.
4. **Fluid Properties** (`constant/transportProperties`):
   - Quick presets for Water (20°C), Air (20°C), Engine Oil, Blood (CFD), and Custom.
   - Direct inputs for kinematic viscosity $\nu$ ($m^2/s$) and density $\rho$ ($kg/m^3$).
5. **Solvers & Relaxation** (`system/fvSolution`):
   - Active algorithm display (`PIMPLE`, `SIMPLE`, `PISO`) and sub-relaxation factors for pressure ($p$) and velocity ($U$).
- **Anti-Scroll Protection**: All dropdowns use `NoScrollComboBox` to prevent accidental value alterations while scrolling through panels.

### Dictionary Code Editor & Real-Time Linter
- Custom `CodeEditor` with line-number gutter, active-line highlight, and Ctrl+wheel font scaling.
- Syntax highlighter supporting standard OpenFOAM dictionaries, macros (`$variable`), and embedded C++ (`#{ ... #}`).
- Find & Replace bar (Ctrl+F) with case-sensitivity and whole-word matching.
- **Smart Debounced Linter** (`gafoam.foamlint`):
  - Validates bracket balance (`{}`, `[]`, `()`) and missing semicolons in real time.
  - Automatically suppresses false positives inside commented blocks and OpenFOAM file headers.

### Real-Time Residuals & Convergence Monitoring
- Interactive chart using `PySide6.QtCharts` plotting initial residuals per field vs. Time or Iteration.
- Automatic collapse of velocity residuals ($Ux, Uy, Uz$) into a single $|U|$ magnitude curve.
- Real-time convergence table matching `residualControl` tolerances from `system/fvSolution`.
- **Divergence Detection**: Automatic detection of numerical instability and residual explosion.

### Automated Technical PDF Report Generator
- Export of technical simulation reports via `ReportGenerator` (`QPdfWriter` + `QPainter`).
- Formats case metadata, dictionary parameters, residual chart pixmap, final convergence status, and solver execution statistics onto structured A4 PDF pages.

### ParaView Launch
- Direct toolbar action that creates a `<case>.foam` stub and launches ParaView pointed at the active case.

---

## Repository Structure

```
GAFoam/
├── main.py                  # Main entry point
├── pyproject.toml           # Package metadata and test configurations
├── requirements.txt         # Runtime dependencies
├── src/gafoam/
│   ├── app.py               # Application bootstrap, fonts, and event loop
│   ├── main_window.py       # Main window layout, dock management, and execution orchestration
│   ├── bc_editor.py         # Visual Boundary Condition editor widget (0/ directory)
│   ├── editor.py            # Code editor with syntax highlighting, find/replace, and linter
│   ├── filebrowser.py       # Case tree view with custom file-type icons
│   ├── foamdict.py          # Pure-Python parser/writer for controlDict, fvSchemes, fvSolution, etc.
│   ├── foamlint.py          # Dictionary syntax validator and linter
│   ├── handlers.py          # Process I/O and execution handlers
│   ├── logparse.py          # Solver log streaming, residual extraction, and metrics parser
│   ├── menus.py             # Global application menus and keyboard shortcuts
│   ├── panels.py            # Case Settings, Convergence Monitor, and Numerical Schemes docks
│   ├── report.py            # PDF technical report generator (QPdfWriter)
│   ├── residuals.py         # Real-time QtCharts residual visualization widget
│   ├── resources.py         # Asset and font resolution helpers
│   ├── stl_viewer.py        # 3D PyVista viewer with clipping planes, ruler, and diagnostics
│   ├── terminal.py          # Embedded bash terminal component
│   ├── fonts/               # Embedded Inter and Fira Code TrueType fonts
│   └── icons/               # SVG toolbar and file-type icons
└── tests/                   # Automated pytest suite (77+ tests)
```

---

## Installation & Running

### Requirements
- **Python 3.10+** (tested on 3.10, 3.11, 3.12, 3.13)
- An OpenFOAM environment sourced in your shell (e.g. OpenFOAM v2012+, v2212+, v2312+, or OpenFOAM-9/10/11)
- Linux / Ubuntu / WSL2 (Windows Subsystem for Linux with WSLg)

### Automated 1-Step Installation (Recommended)
Run the automated installer in your current shell:
```bash
source ./install.sh
```
*(or `./install.sh`)*
This will:
1. Create a dedicated virtual environment in `~/.local/share/gafoam/venv`.
2. Automatically install all required dependencies and the `gafoam` package.
3. Create the `gafoam` executable in `~/.local/bin` (added to your `PATH`).
4. Auto-configure ABNT2 Brazilian keyboard support and desktop application entry.

Once installed, simply run from any directory without needing to activate any virtual environment:
```bash
gafoam
# or open a specific case directly:
gafoam /path/to/openfoam/case
```

### Manual Installation
```bash
pip install -r requirements.txt
python3 main.py
```

---

## Testing

Run the automated test suite with `pytest`:

```bash
pytest -v
```

All 77 unit and integration tests validate dictionary read/write, syntax linting, log parsing, case integrity checks, and GUI module imports.

---

## Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| **Ctrl+R** | Run Case Simulation (`Allrun`) |
| **Ctrl+S** | Save Active Dictionary File |
| **Ctrl+Shift+S** | Save File As... |
| **Ctrl+F** | Open Find & Replace Bar |
| **Esc** | Close Find & Replace Bar |
| **Ctrl+0** | Reset Editor Zoom / Scale |
| **Ctrl+Wheel** | Zoom In / Out Editor Font |

---

## License
This project is open-source and available under the MIT License.
