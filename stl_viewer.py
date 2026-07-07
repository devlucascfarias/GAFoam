import os
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel

class STLViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        try:
            self.plotter = QtInteractor(self)
            self.layout.addWidget(self.plotter.interactor)
            self.plotter.set_background("white")
        except Exception as e:
            from PySide6.QtWidgets import QLabel
            self.layout.addWidget(QLabel(f"Erro ao inicializar visualizador 3D: {e}"))
            self.plotter = None

    def load_stl(self, file_path):
        if not self.plotter:
            return
            
        try:
            self.plotter.clear()
            mesh = None
            
            try:
                mesh = pv.read(file_path)
                if mesh.n_points == 0:
                    mesh = None
            except Exception:
                mesh = None

            if mesh is None:
                try:
                    import numpy as np
                    vertices = []
                    
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            line = line.strip().lower()
                            if line.startswith('vertex'):
                                parts = line.split()
                                if len(parts) >= 4:
                                    try:
                                        v = [float(x) for x in parts[1:4]]
                                        vertices.append(v)
                                    except ValueError:
                                        continue
                    
                    if vertices:
                        v_np = np.array(vertices)
                        n_faces = len(vertices) // 3
                        if n_faces > 0:
                            faces = np.column_stack([
                                np.full(n_faces, 3), 
                                np.arange(0, n_faces*3).reshape(-1, 3)
                             ]).flatten()
                            mesh = pv.PolyData(v_np, faces)
                except Exception as e:
                    print(f"Falha no parser manual: {e}")

            if mesh and mesh.n_points > 0:
                self.plotter.add_mesh(mesh, color='silver', show_edges=True, opacity=0.8)
                self.plotter.add_axes()
                self.plotter.view_isometric()
                self.plotter.reset_camera()
            else:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Aviso", f"O arquivo '{os.path.basename(file_path)}' não pôde ser interpretado como um STL/geometria válida.")
                
        except Exception as e:
            print(f"Erro ao carregar geometria: {e}")

    def closeEvent(self, event):
        if self.plotter:
            self.plotter.close()
        super().closeEvent(event)


class CaseGeometryWidget(QWidget):
    """Aba dedicada para escanear e exibir geometrias (STL/OBJ) do caso OpenFOAM ativo."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        
        # Barra superior de seleção de arquivos de geometria
        controls = QHBoxLayout()
        self.lbl = QLabel("Arquivo de Geometria:")
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self.load_selected)
        
        self.btn_refresh = QPushButton("Atualizar Lista")
        self.btn_refresh.clicked.connect(self.refresh_scan)
        
        controls.addWidget(self.lbl)
        controls.addWidget(self.combo, 1)
        controls.addWidget(self.btn_refresh)
        layout.addLayout(controls)
        
        # Visualizador 3D
        self.viewer = STLViewer(self)
        layout.addWidget(self.viewer)
        
        self.current_case_path = None
        self.scan_case(None) # Configura estado inicial vazio

    def scan_case(self, case_path):
        """Varre o diretório do caso buscando geometrias e atualiza o combobox."""
        self.current_case_path = case_path
        
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.blockSignals(False)
        
        if not case_path or not os.path.isdir(case_path):
            self.combo.addItem("Abra um caso OpenFOAM para visualizar a geometria", "")
            self.combo.setEnabled(False)
            self.btn_refresh.setEnabled(False)
            return
            
        found_files = []
        try:
            # Varre pastas do caso, ignorando binários, compilações e ambientes virtuais
            for root, dirs, files in os.walk(case_path):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('platforms', 'processor', 'venv', '.venv', 'pycache')]
                for file in files:
                    if file.lower().endswith(('.stl', '.obj')):
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, case_path)
                        found_files.append((rel_path, full_path))
        except Exception as e:
            print(f"Erro ao escanear pasta do caso: {e}")
            
        if found_files:
            found_files.sort(key=lambda x: x[0].lower())
            
            self.combo.blockSignals(True)
            for rel, full in found_files:
                self.combo.addItem(rel, full)
            self.combo.blockSignals(False)
            
            self.combo.setEnabled(True)
            self.btn_refresh.setEnabled(True)
            self.load_selected()
        else:
            self.combo.addItem("Nenhuma geometria encontrada (.stl, .obj) no caso aberto", "")
            self.combo.setEnabled(False)
            self.btn_refresh.setEnabled(True)
            if self.viewer.plotter:
                self.viewer.plotter.clear()

    def refresh_scan(self):
        if self.current_case_path:
            self.scan_case(self.current_case_path)
            
    def load_selected(self):
        full_path = self.combo.currentData()
        if full_path and os.path.exists(full_path):
            self.viewer.load_stl(full_path)
