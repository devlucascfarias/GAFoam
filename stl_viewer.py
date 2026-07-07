import os
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel, QScrollArea, QCheckBox
from PySide6.QtCore import Qt

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
        self.actors = {}
        
        # Paleta de cores para múltiplas geometrias
        self._mesh_colors = [
            "#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6",
            "#06b6d4", "#ec4899", "#84cc16", "#78716c", "#64748b"
        ]

    def load_meshes(self, files_list):
        """Carrega e renderiza simultaneamente todas as malhas listadas com cores distintas."""
        if not self.plotter:
            return
            
        self.plotter.clear()
        self.actors = {}
        
        for idx, (rel_path, full_path) in enumerate(files_list):
            try:
                mesh = None
                try:
                    mesh = pv.read(full_path)
                    if mesh.n_points == 0:
                        mesh = None
                except Exception:
                    mesh = None

                # Parser manual como fallback
                if mesh is None:
                    import numpy as np
                    vertices = []
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
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

                if mesh and mesh.n_points > 0:
                    color = self._mesh_colors[idx % len(self._mesh_colors)]
                    actor = self.plotter.add_mesh(mesh, color=color, show_edges=True, opacity=0.75, name=rel_path)
                    self.actors[full_path] = actor
            except Exception as e:
                print(f"Erro ao carregar mesh {rel_path}: {e}")

        if self.actors:
            self.plotter.add_axes()
            self.plotter.view_isometric()
            self.plotter.reset_camera()

    def set_mesh_visibility(self, file_path, visible):
        """Controla a visibilidade em tempo real de uma malha específica."""
        actor = self.actors.get(file_path)
        if actor:
            actor.SetVisibility(visible)
            # Força o VTK a renderizar o frame atualizado
            self.plotter.render()

    def closeEvent(self, event):
        if self.plotter:
            self.plotter.close()
        super().closeEvent(event)


class CaseGeometryWidget(QWidget):
    """Painel lateral interativo que exibe a lista de geometrias e permite ocultá-las/exibi-las."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Painel lateral esquerdo (Sidebar) para os checkboxes
        self.sidebar = QWidget(self)
        self.sidebar.setFixedWidth(240)
        self.sidebar.setStyleSheet(
            "QWidget { background-color: #f1f3f5; border-right: 1px solid #dee2e6; }"
            "QLabel { background-color: transparent; }"
            "QCheckBox { background-color: transparent; }"
        )
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(8, 8, 8, 8)
        
        # Cabeçalho da barra lateral
        header_layout = QHBoxLayout()
        header_lbl = QLabel("Geometrias (.stl, .obj)")
        header_lbl.setStyleSheet("font-weight: bold; font-size: 10pt; color: #495057;")
        self.btn_refresh = QPushButton("Atualizar")
        self.btn_refresh.setStyleSheet("padding: 3px 8px; font-size: 8pt;")
        self.btn_refresh.clicked.connect(self.refresh_scan)
        header_layout.addWidget(header_lbl, 1)
        header_layout.addWidget(self.btn_refresh)
        sidebar_layout.addLayout(header_layout)
        
        # Área de rolagem para os Checkboxes
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border: none; background: transparent;")
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.checkboxes_layout = QVBoxLayout(self.scroll_content)
        self.checkboxes_layout.setContentsMargins(0, 4, 0, 4)
        self.checkboxes_layout.setSpacing(6)
        self.checkboxes_layout.addStretch(1)
        
        self.scroll.setWidget(self.scroll_content)
        sidebar_layout.addWidget(self.scroll, 1)
        
        main_layout.addWidget(self.sidebar)
        
        # Visualizador 3D acoplado ao lado direito
        self.viewer = STLViewer(self)
        main_layout.addWidget(self.viewer, 1)
        
        self.current_case_path = None
        self.checkboxes = {}
        self.scan_case(None)

    def scan_case(self, case_path):
        """Varre o projeto, cria os checkboxes e plota todas as malhas."""
        self.current_case_path = case_path
        
        # Remove checkboxes antigos de forma limpa
        for cb in self.checkboxes.values():
            cb.setParent(None)
            cb.deleteLater()
        self.checkboxes = {}
        
        while self.checkboxes_layout.count() > 0:
            item = self.checkboxes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        if not case_path or not os.path.isdir(case_path):
            placeholder = QLabel("Abra um caso OpenFOAM")
            placeholder.setStyleSheet("color: #8c9197; font-style: italic;")
            self.checkboxes_layout.addWidget(placeholder)
            self.checkboxes_layout.addStretch(1)
            self.btn_refresh.setEnabled(False)
            if self.viewer.plotter:
                self.viewer.plotter.clear()
            return
            
        self.btn_refresh.setEnabled(True)
        found_files = []
        try:
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
            
            # Carrega e exibe todos de uma vez
            self.viewer.load_meshes(found_files)
            
            # Cria um checkbox dinâmico para cada malha
            for rel, full in found_files:
                cb = QCheckBox(rel)
                cb.setChecked(True)
                cb.toggled.connect(lambda checked, path=full: self.viewer.set_mesh_visibility(path, checked))
                self.checkboxes_layout.addWidget(cb)
                self.checkboxes[full] = cb
                
            self.checkboxes_layout.addStretch(1)
        else:
            placeholder = QLabel("Nenhuma geometria encontrada")
            placeholder.setStyleSheet("color: #8c9197; font-style: italic;")
            self.checkboxes_layout.addWidget(placeholder)
            self.checkboxes_layout.addStretch(1)
            if self.viewer.plotter:
                self.viewer.plotter.clear()

    def refresh_scan(self):
        if self.current_case_path:
            self.scan_case(self.current_case_path)
