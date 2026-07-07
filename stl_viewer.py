import os
import time
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
                             QPushButton, QLabel, QScrollArea, QCheckBox, 
                             QListWidget, QListWidgetItem, QSlider, QGroupBox, 
                             QFormLayout, QFileDialog)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QIcon

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
        self.meshes = {} # Armazena os objetos pyvista.PolyData para leitura de metadados
        
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
        self.meshes = {}
        
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
                    actor = self.plotter.add_mesh(mesh, color=color, show_edges=True, opacity=0.8, name=rel_path)
                    self.actors[full_path] = actor
                    self.meshes[full_path] = mesh
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
            self.plotter.render()

    def closeEvent(self, event):
        if self.plotter:
            self.plotter.close()
        super().closeEvent(event)


class CaseGeometryWidget(QWidget):
    """Painel lateral duplo com controle de árvore, visualizador 3D e menu de inspeção à direita."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 1. Painel lateral esquerdo (Listagem de Geometrias)
        self.sidebar_left = QWidget(self)
        self.sidebar_left.setFixedWidth(200)
        self.sidebar_left.setStyleSheet(
            "QWidget { background-color: #f1f3f5; border-right: 1px solid #dee2e6; }"
            "QLabel { background-color: transparent; font-weight: bold; color: #495057; }"
            "QListWidget { background-color: #ffffff; border: 1px solid #ced4da; border-radius: 4px; }"
        )
        left_layout = QVBoxLayout(self.sidebar_left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        
        header_left = QHBoxLayout()
        header_lbl_left = QLabel("Geometrias")
        self.btn_refresh = QPushButton("Atualizar")
        self.btn_refresh.setStyleSheet("padding: 2px 6px; font-size: 8pt;")
        self.btn_refresh.clicked.connect(self.refresh_scan)
        header_left.addWidget(header_lbl_left, 1)
        header_left.addWidget(self.btn_refresh)
        left_layout.addLayout(header_left)
        
        self.mesh_list = QListWidget(self)
        self.mesh_list.itemChanged.connect(self.on_mesh_item_changed)
        self.mesh_list.currentItemChanged.connect(self.on_mesh_selection_changed)
        left_layout.addWidget(self.mesh_list, 1)
        
        main_layout.addWidget(self.sidebar_left)
        
        # 2. Visualizador 3D (Centro)
        self.viewer = STLViewer(self)
        main_layout.addWidget(self.viewer, 1)
        
        # 3. Painel lateral direito (Propriedades e Ferramentas)
        self.sidebar_right = QWidget(self)
        self.sidebar_right.setFixedWidth(260)
        self.sidebar_right.setStyleSheet(
            "QWidget { background-color: #f1f3f5; border-left: 1px solid #dee2e6; }"
            "QGroupBox { font-weight: bold; color: #495057; border: 1px solid #ced4da; border-radius: 4px; margin-top: 8px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }"
            "QLabel { background-color: transparent; color: #212529; }"
        )
        right_layout = QVBoxLayout(self.sidebar_right)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(10)
        
        # Grupo 1: Estilização / Aparência
        self.group_style = QGroupBox("Propriedades de Exibição", self)
        style_layout = QFormLayout(self.group_style)
        style_layout.setContentsMargins(8, 8, 8, 8)
        style_layout.setSpacing(6)
        
        self.combo_rep = QComboBox()
        self.combo_rep.addItem("Superfície + Linhas", "surface_edges")
        self.combo_rep.addItem("Apenas Superfície", "surface")
        self.combo_rep.addItem("Arestas (Wireframe)", "wireframe")
        self.combo_rep.addItem("Nuvem de Pontos", "points")
        self.combo_rep.currentIndexChanged.connect(self.change_representation)
        
        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(80)
        self.slider_opacity.valueChanged.connect(self.change_opacity)
        
        style_layout.addRow("Aparência:", self.combo_rep)
        style_layout.addRow("Opacidade:", self.slider_opacity)
        right_layout.addWidget(self.group_style)
        
        # Grupo 2: Informações da malha selecionada
        self.group_info = QGroupBox("Informações Físicas", self)
        info_layout = QFormLayout(self.group_info)
        info_layout.setContentsMargins(8, 8, 8, 8)
        info_layout.setSpacing(6)
        
        self.lbl_points = QLabel("-")
        self.lbl_cells = QLabel("-")
        self.lbl_bound_x = QLabel("-")
        self.lbl_bound_y = QLabel("-")
        self.lbl_bound_z = QLabel("-")
        
        info_layout.addRow("Pontos:", self.lbl_points)
        info_layout.addRow("Células/Triâng.:", self.lbl_cells)
        info_layout.addRow("Limites X:", self.lbl_bound_x)
        info_layout.addRow("Limites Y:", self.lbl_bound_y)
        info_layout.addRow("Limites Z:", self.lbl_bound_z)
        right_layout.addWidget(self.group_info)
        
        # Grupo 3: Câmera e Captura
        self.group_cam = QGroupBox("Câmera e Exportação", self)
        cam_layout = QVBoxLayout(self.group_cam)
        cam_layout.setContentsMargins(8, 8, 8, 8)
        cam_layout.setSpacing(8)
        
        grid_cam = QHBoxLayout()
        self.btn_iso = QPushButton("Iso")
        self.btn_iso.clicked.connect(lambda: self.set_cam_view("iso"))
        self.btn_xy = QPushButton("Top")
        self.btn_xy.clicked.connect(lambda: self.set_cam_view("xy"))
        self.btn_xz = QPushButton("Front")
        self.btn_xz.clicked.connect(lambda: self.set_cam_view("xz"))
        
        grid_cam.addWidget(self.btn_iso)
        grid_cam.addWidget(self.btn_xy)
        grid_cam.addWidget(self.btn_xz)
        cam_layout.addLayout(grid_cam)
        
        self.btn_screenshot = QPushButton("Capturar Tela")
        self.btn_screenshot.clicked.connect(self.take_screenshot)
        cam_layout.addWidget(self.btn_screenshot)
        
        right_layout.addWidget(self.group_cam)
        right_layout.addStretch(1)
        
        main_layout.addWidget(self.sidebar_right)
        
        self.current_case_path = None
        self.scan_case(None)

    def scan_case(self, case_path):
        """Varre o projeto, popula a lista e renderiza as malhas."""
        self.current_case_path = case_path
        
        # Limpa estados
        self.mesh_list.clear()
        
        # Reseta labels
        self.lbl_points.setText("-")
        self.lbl_cells.setText("-")
        self.lbl_bound_x.setText("-")
        self.lbl_bound_y.setText("-")
        self.lbl_bound_z.setText("-")
        self.group_style.setEnabled(False)
        self.group_info.setEnabled(False)
        self.group_cam.setEnabled(False)
        
        if not case_path or not os.path.isdir(case_path):
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
            print(f"Erro ao escanear geometria: {e}")
            
        if found_files:
            found_files.sort(key=lambda x: x[0].lower())
            
            # Carrega no visualizador 3D
            self.viewer.load_meshes(found_files)
            
            # Popula QListWidget com itens marcáveis
            self.mesh_list.blockSignals(True)
            mesh_icon = self.create_mesh_icon()
            for rel, full in found_files:
                name_only = os.path.basename(full)
                item = QListWidgetItem(name_only)
                item.setIcon(mesh_icon)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, full) # Salva o caminho no próprio item
                self.mesh_list.addItem(item)
            self.mesh_list.blockSignals(False)
            
            self.group_cam.setEnabled(True)
            # Seleciona o primeiro por padrão para exibir propriedades
            if self.mesh_list.count() > 0:
                self.mesh_list.setCurrentRow(0)
        else:
            if self.viewer.plotter:
                self.viewer.plotter.clear()

    def refresh_scan(self):
        if self.current_case_path:
            self.scan_case(self.current_case_path)

    def on_mesh_item_changed(self, item):
        """Oculta/exibe malha com base no checkbox."""
        full_path = item.data(Qt.UserRole) if item else None
        if full_path:
            is_checked = (item.checkState() == Qt.Checked)
            self.viewer.set_mesh_visibility(full_path, is_checked)

    def on_mesh_selection_changed(self, current, previous):
        """Atualiza a barra lateral direita com as propriedades da malha selecionada."""
        full_path = current.data(Qt.UserRole) if current else None
        if not full_path:
            self.group_style.setEnabled(False)
            self.group_info.setEnabled(False)
            return
            
        self.group_style.setEnabled(True)
        self.group_info.setEnabled(True)
        
        # 1. Recupera o mesh e atualiza metadados
        mesh = self.viewer.meshes.get(full_path)
        if mesh:
            self.lbl_points.setText(f"{mesh.n_points:,}")
            self.lbl_cells.setText(f"{mesh.n_cells:,}")
            b = mesh.bounds # (xmin, xmax, ymin, ymax, zmin, zmax)
            self.lbl_bound_x.setText(f"[{b[0]:.3f}, {b[1]:.3f}] m")
            self.lbl_bound_y.setText(f"[{b[2]:.3f}, {b[3]:.3f}] m")
            self.lbl_bound_z.setText(f"[{b[4]:.3f}, {b[5]:.3f}] m")
        else:
            self.lbl_points.setText("Erro")
            self.lbl_cells.setText("Erro")
            self.lbl_bound_x.setText("-")
            self.lbl_bound_y.setText("-")
            self.lbl_bound_z.setText("-")
            
        # 2. Recupera o actor e sincroniza controles de aparência
        actor = self.viewer.actors.get(full_path)
        if actor:
            self.slider_opacity.blockSignals(True)
            self.slider_opacity.setValue(int(actor.GetProperty().GetOpacity() * 100))
            self.slider_opacity.blockSignals(False)
            
            # Sincroniza combobox de representação
            rep = actor.GetProperty().GetRepresentation()
            self.combo_rep.blockSignals(True)
            if rep == 0: # Points
                self.combo_rep.setCurrentIndex(3)
            elif rep == 1: # Wireframe
                self.combo_rep.setCurrentIndex(2)
            elif rep == 2: # Surface
                if actor.GetProperty().GetEdgeVisibility():
                    self.combo_rep.setCurrentIndex(0)
                else:
                    self.combo_rep.setCurrentIndex(1)
            self.combo_rep.blockSignals(False)

    def change_representation(self, index=None):
        """Altera o estilo de renderização da malha selecionada."""
        current_item = self.mesh_list.currentItem()
        full_path = current_item.data(Qt.UserRole) if current_item else None
        actor = self.viewer.actors.get(full_path) if full_path else None
        
        if actor:
            rep_type = self.combo_rep.currentData()
            prop = actor.GetProperty()
            
            if rep_type == "surface_edges":
                prop.SetRepresentationToSurface()
                prop.SetEdgeVisibility(True)
            elif rep_type == "surface":
                prop.SetRepresentationToSurface()
                prop.SetEdgeVisibility(False)
            elif rep_type == "wireframe":
                prop.SetRepresentationToWireframe()
            elif rep_type == "points":
                prop.SetRepresentationToPoints()
                
            self.viewer.plotter.render()

    def change_opacity(self, val):
        """Altera a transparência da malha selecionada."""
        current_item = self.mesh_list.currentItem()
        full_path = current_item.data(Qt.UserRole) if current_item else None
        actor = self.viewer.actors.get(full_path) if full_path else None
        
        if actor:
            actor.GetProperty().SetOpacity(val / 100.0)
            self.viewer.plotter.render()

    def set_cam_view(self, view):
        """Muda o ângulo de visualização da câmera."""
        if not self.viewer.plotter:
            return
        if view == "iso":
            self.viewer.plotter.view_isometric()
        elif view == "xy":
            self.viewer.plotter.view_xy()
        elif view == "xz":
            self.viewer.plotter.view_xz()
        self.viewer.plotter.reset_camera()

    def take_screenshot(self):
        """Salva uma captura da janela 3D na pasta do caso."""
        if not self.viewer.plotter or not self.current_case_path:
            return
            
        timestamp = int(time.time())
        default_name = f"screenshot_geometria_{timestamp}.png"
        
        # Abre diálogo para salvar
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Salvar Captura de Tela", 
            os.path.join(self.current_case_path, default_name),
            "Imagens PNG (*.png)"
        )
        
        if file_path:
            try:
                self.viewer.plotter.screenshot(file_path)
                if hasattr(self.main_window, 'log'):
                    self.main_window.log(f"Captura de tela salva com sucesso em: {file_path}\n")
            except Exception as e:
                print(f"Erro ao salvar screenshot: {e}")

    def create_mesh_icon(self):
        """Desenha programaticamente um ícone vetorial de malha STL/OBJ."""
        from PySide6.QtCore import QPoint
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        pen = QPen(QColor("#1a73e8"))
        pen.setWidthF(1.5)
        painter.setPen(pen)
        
        # Desenha um tetraedro tridimensional (ícone de grade/mesh)
        p1 = QPoint(8, 2)
        p2 = QPoint(2, 12)
        p3 = QPoint(14, 12)
        p4 = QPoint(8, 8)
        
        painter.drawLine(p1, p2)
        painter.drawLine(p2, p3)
        painter.drawLine(p3, p1)
        painter.drawLine(p1, p4)
        painter.drawLine(p2, p4)
        painter.drawLine(p3, p4)
        
        painter.end()
        return QIcon(pixmap)
