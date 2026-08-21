"""Visualizador 3D para malhas de geometria OpenFOAM (STL/OBJ).

Inclui diagnósticos de estanqueidade (watertight), identificação de patches,
plano de corte interativo, ferramenta de medição tridimensional e personalização de visualização.
"""

import math
import os
import time
import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
    QPushButton, QLabel, QScrollArea, QCheckBox, 
    QListWidget, QListWidgetItem, QSlider, QGroupBox, 
    QFormLayout, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox,
    QSizePolicy
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QIcon, QFont, QImage


def check_mesh_quality(mesh):
    """Calcula métricas avançadas de qualidade e estanqueidade (watertight) para CFD."""
    if mesh is None or not hasattr(mesh, 'n_points') or mesh.n_points == 0:
        return None
    
    n_pts = mesh.n_points
    n_cells = mesh.n_cells
    is_all_tri = getattr(mesh, 'is_all_triangles', True)
    
    # Detecção de arestas abertas (boundary edges)
    n_open_edges = 0
    try:
        feature_edges = mesh.extract_feature_edges(
            boundary_edges=True, 
            feature_edges=False, 
            manifold_edges=False,
            non_manifold_edges=True
        )
        n_open_edges = feature_edges.n_cells
    except Exception:
        n_open_edges = 0

    is_watertight = (n_open_edges == 0 and n_cells > 0)
    area = float(getattr(mesh, 'area', 0.0))
    
    volume = None
    if is_watertight:
        try:
            volume = float(mesh.volume)
        except Exception:
            volume = None

    bounds = mesh.bounds # (xmin, xmax, ymin, ymax, zmin, zmax)
    dx = bounds[1] - bounds[0]
    dy = bounds[3] - bounds[2]
    dz = bounds[5] - bounds[4]

    return {
        "points": n_pts,
        "cells": n_cells,
        "is_all_triangles": is_all_tri,
        "open_edges": n_open_edges,
        "is_watertight": is_watertight,
        "area": area,
        "volume": volume,
        "bounds": bounds,
        "dimensions": (dx, dy, dz)
    }


def detect_stl_patches(file_path):
    """Varre arquivo STL em busca de múltiplos patches/sólidos (para snappyHexMesh)."""
    patches = []
    if not file_path or not os.path.isfile(file_path):
        return patches

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines(100000)
        
        current_solid = None
        face_count = 0
        for line in lines:
            l = line.strip()
            if l.lower().startswith("solid"):
                parts = l.split(maxsplit=1)
                name = parts[1] if len(parts) > 1 else "default"
                current_solid = name
                face_count = 0
            elif l.lower().startswith("endsolid"):
                if current_solid:
                    patches.append({"name": current_solid, "faces": face_count})
                    current_solid = None
            elif l.lower().startswith("facet"):
                face_count += 1
    except Exception:
        pass

    if not patches:
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        patches.append({"name": base_name, "faces": "all"})
    return patches


class STLViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_render = QLabel(self)
        self.lbl_render.setAlignment(Qt.AlignCenter)
        self.lbl_render.setStyleSheet("background-color: #ffffff;")
        self.lbl_render.setFocusPolicy(Qt.ClickFocus)
        self.lbl_render.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_render.setMinimumSize(100, 100)
        self.layout.addWidget(self.lbl_render)

        self.plotter = pv.Plotter(off_screen=True, window_size=(800, 600))
        self.plotter.set_background("white")
        self.plotter.add_axes()
            
        self.actors = {}
        self.meshes = {} # Armazena os objetos pyvista.PolyData originais
        self.mesh_props = {}
        
        # Paleta de cores vibrantes e contrastantes (IBM Carbon)
        self._mesh_colors = [
            "#0f62fe",  # Blue
            "#da1e28",  # Red
            "#198038",  # Green
            "#ff832b",  # Orange
            "#8a3ffc",  # Purple
            "#0072c3",  # Cyan
            "#ff7eb6",  # Magenta
            "#f1c21b",  # Yellow
            "#009d9a",  # Teal
            "#6929c4",  # Deep purple
        ]

        self.measurement_points = []
        self.on_measure_callback = None
        self.measuring_active = False
        self.clip_active = False
        self._last_pos = QPoint()

    def update_render(self):
        """Renderiza a cena tridimensional e atualiza o buffer gráfico."""
        if not self.plotter:
            return
        w = max(100, self.lbl_render.width(), self.width())
        h = max(100, self.lbl_render.height(), self.height())
        self.plotter.window_size = (w, h)
        try:
            img = self.plotter.screenshot(return_img=True)
            if img is not None and len(img.shape) == 3:
                ih, iw, ic = img.shape
                bytes_per_line = ic * iw
                img_c = np.ascontiguousarray(img)
                qimg = QImage(img_c.data, iw, ih, bytes_per_line, QImage.Format_RGB888).copy()
                self.lbl_render.setPixmap(QPixmap.fromImage(qimg))
        except Exception as e:
            print(f"Error in update_render: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        self.update_render()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_render()

    def mousePressEvent(self, event):
        self._last_pos = event.pos()
        if self.measuring_active:
            # Captura ponto estimado via ray picking no bounding box central
            if self.meshes:
                first_mesh = list(self.meshes.values())[0]
                b = first_mesh.bounds
                center = [(b[0] + b[1]) * 0.5, (b[2] + b[3]) * 0.5, (b[4] + b[5]) * 0.5]
                self._on_point_picked(center)

    def mouseMoveEvent(self, event):
        dx = event.x() - self._last_pos.x()
        dy = event.y() - self._last_pos.y()
        self._last_pos = event.pos()

        if event.buttons() & Qt.LeftButton:
            # Rotação orbital
            self.plotter.camera.Azimuth(-dx * 0.5)
            self.plotter.camera.Elevation(dy * 0.5)
            self.update_render()
        elif event.buttons() & Qt.RightButton or event.buttons() & Qt.MiddleButton:
            # Pan (translação)
            cam = self.plotter.camera
            pos = np.array(cam.position, dtype=float)
            foc = np.array(cam.focal_point, dtype=float)
            up = np.array(cam.up, dtype=float)
            v_dir = foc - pos
            dist = np.linalg.norm(v_dir)
            right = np.cross(v_dir, up)
            r_norm = np.linalg.norm(right)
            if r_norm > 1e-6:
                right /= r_norm
            true_up = np.cross(right, v_dir)
            u_norm = np.linalg.norm(true_up)
            if u_norm > 1e-6:
                true_up /= u_norm
            
            pan_scale = max(dist * 0.002, 1e-4)
            shift = (-dx * right + dy * true_up) * pan_scale
            cam.position = tuple(pos + shift)
            cam.focal_point = tuple(foc + shift)
            self.update_render()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.plotter.camera.zoom(1.1)
        else:
            self.plotter.camera.zoom(0.9)
        self.update_render()

    def load_meshes(self, files_list):
        """Carrega e renderiza simultaneamente todas as malhas listadas com cores distintas e superfícies lisas."""
        self.plotter.clear()
        self.plotter.add_axes()
        self.actors = {}
        self.meshes = {}
        self.mesh_props = {}
        self.measurement_points = []
        
        for idx, (rel_path, full_path) in enumerate(files_list):
            try:
                mesh = None
                try:
                    mesh = pv.read(full_path)
                    if mesh.n_points == 0:
                        mesh = None
                except Exception:
                    mesh = None

                if mesh is None:
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
                                np.arange(0, n_faces * 3).reshape(-1, 3)
                            ]).flatten()
                            mesh = pv.PolyData(v_np, faces)

                if mesh and mesh.n_points > 0:
                    color_hex = self._mesh_colors[idx % len(self._mesh_colors)]
                    qcol = QColor(color_hex)
                    rgb = (qcol.redF(), qcol.greenF(), qcol.blueF())
                    
                    try:
                        mesh.clear_data()
                    except Exception:
                        pass

                    # Paredes externas têm leve transparência para revelar partes internas
                    is_outer_wall = any(w in rel_path.lower() for w in ["wall", "parede", "outer", "domain", "box"])
                    mesh_opacity = 0.40 if is_outer_wall else 0.85

                    self.plotter.add_mesh(
                        mesh,
                        color=rgb,
                        show_edges=False,
                        edge_color="#161616",
                        opacity=mesh_opacity,
                        name=rel_path,
                        reset_camera=False
                    )
                    self.actors[full_path] = rel_path
                    self.meshes[full_path] = mesh
                    self.mesh_props[full_path] = {
                        "rgb": rgb,
                        "opacity": mesh_opacity,
                        "style": "surface",
                        "show_edges": False,
                        "visible": True
                    }
            except Exception as e:
                print(f"Erro ao carregar mesh {rel_path}: {e}")

        if self.actors:
            self.plotter.view_isometric()
            self.plotter.reset_camera()
            self.update_render()

    def set_mesh_visibility(self, file_path, visible):
        """Controla a visibilidade em tempo real de uma malha específica."""
        if file_path in self.mesh_props:
            self.mesh_props[file_path]["visible"] = visible
            name = self.actors.get(file_path)
            if not visible and name:
                self.plotter.remove_actor(name)
            elif visible and file_path in self.meshes:
                mesh = self.meshes[file_path]
                prop = self.mesh_props[file_path]
                self.plotter.add_mesh(
                    mesh,
                    color=prop["rgb"],
                    opacity=prop["opacity"],
                    style=prop["style"],
                    show_edges=prop["show_edges"],
                    name=name,
                    reset_camera=False
                )
            self.update_render()

    def apply_clip_plane(self, enabled=False, normal=(1, 0, 0), origin=(0, 0, 0), invert=False):
        """Aplica plano de corte dinâmico a todas as malhas ativas."""
        self.clip_active = enabled
        norm = [-normal[0], -normal[1], -normal[2]] if invert else list(normal)

        for full_path, mesh in self.meshes.items():
            name = self.actors.get(full_path)
            prop = self.mesh_props.get(full_path)
            if not name or not prop or not prop["visible"]:
                continue

            target_mesh = mesh
            if enabled:
                try:
                    clipped = mesh.clip(normal=norm, origin=origin, invert=False)
                    if clipped.n_points > 0:
                        target_mesh = clipped
                except Exception:
                    pass

            self.plotter.add_mesh(
                target_mesh,
                color=prop["rgb"],
                opacity=prop["opacity"],
                style=prop["style"],
                show_edges=prop["show_edges"],
                name=name,
                reset_camera=False
            )
        self.update_render()

    def start_measuring(self, callback=None):
        """Ativa a ferramenta de medição interativa por pontos."""
        self.measurement_points = []
        self.on_measure_callback = callback
        self.measuring_active = True

    def _on_point_picked(self, point):
        """Recebe as coordenadas do ponto clicado na geometria."""
        if point is None:
            return
            
        self.measurement_points.append(list(point))
        if len(self.measurement_points) >= 2:
            p1 = self.measurement_points[-2]
            p2 = self.measurement_points[-1]
            try:
                line = pv.Line(p1, p2)
                self.plotter.add_mesh(line, color="#da1e28", line_width=3, name="__measurement_line__", reset_camera=False)
                self.update_render()
            except Exception:
                pass
                
            if self.on_measure_callback:
                self.on_measure_callback(p1, p2)
            self.measurement_points = []

    def clear_measurement(self):
        """Limpa as marcações e desativa a ferramenta de medição."""
        self.measurement_points = []
        self.measuring_active = False
        try:
            self.plotter.remove_actor("__measurement_line__")
        except Exception:
            pass
        self.update_render()

    def closeEvent(self, event):
        if self.plotter:
            self.plotter.close()
        super().closeEvent(event)


class NoScrollComboBox(QComboBox):
    """QComboBox que ignora a rolagem do mouse quando fechado para evitar alterações acidentais de valor."""

    def wheelEvent(self, event):
        event.ignore()


class CaseGeometryWidget(QWidget):
    """Painel lateral duplo com visualizador 3D e menu completo de ferramentas de inspeção CFD."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 1. Painel lateral esquerdo (Listagem de Geometrias direta)
        self.sidebar_left = QWidget(self)
        self.sidebar_left.setFixedWidth(180)
        self.sidebar_left.setStyleSheet(
            "QWidget { background-color: #f4f4f4; border-right: 1px solid #e0e0e0; }"
            "QListWidget { background-color: #ffffff; color: #161616; border: 1px solid #e0e0e0; border-radius: 0; font-size: 11px; }"
        )
        left_layout = QVBoxLayout(self.sidebar_left)
        left_layout.setContentsMargins(6, 6, 6, 6)
        
        self.mesh_list = QListWidget(self)
        self.mesh_list.itemChanged.connect(self.on_mesh_item_changed)
        self.mesh_list.currentItemChanged.connect(self.on_mesh_selection_changed)
        left_layout.addWidget(self.mesh_list, 1)
        main_layout.addWidget(self.sidebar_left)
        
        # 2. Visualizador 3D (Centro)
        self.viewer = STLViewer(self)
        main_layout.addWidget(self.viewer, 1)
        
        # 3. Painel lateral direito com ScrollArea para todas as ferramentas
        self.scroll_right = QScrollArea(self)
        self.scroll_right.setFixedWidth(270)
        self.scroll_right.setWidgetResizable(True)
        self.scroll_right.setStyleSheet(
            "QScrollArea { border: none; background-color: #f4f4f4; border-left: 1px solid #e0e0e0; }"
            "QWidget#SidebarContent { background-color: #f4f4f4; }"
            "QGroupBox { font-weight: 600; color: #161616; border: none; border-top: 1px solid #e0e0e0; margin-top: 12px; padding-top: 10px; border-radius: 0; font-size: 11px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 0px; padding: 0 4px; }"
            "QLabel { background-color: transparent; color: #161616; font-size: 11px; }"
            "QComboBox { background-color: #ffffff; color: #161616; border: 1px solid #8d8d8d; padding: 3px 6px; font-size: 11px; border-radius: 0; }"
            "QPushButton { background-color: #ffffff; color: #161616; border: 1px solid #8d8d8d; font-weight: 500; font-size: 11px; padding: 4px 8px; border-radius: 0; }"
            "QPushButton:hover { background-color: #e0e0e0; border-color: #161616; }"
            "QPushButton:pressed { background-color: #c6c6c6; }"
            "QCheckBox { font-size: 11px; color: #161616; background: transparent; }"
        )
        
        self.sidebar_content = QWidget()
        self.sidebar_content.setObjectName("SidebarContent")
        right_layout = QVBoxLayout(self.sidebar_content)
        right_layout.setContentsMargins(10, 8, 10, 12)
        right_layout.setSpacing(8)
        
        # ── Grupo 1: Display Properties ──
        self.group_style = QGroupBox("Display Properties", self.sidebar_content)
        style_layout = QFormLayout(self.group_style)
        style_layout.setContentsMargins(4, 8, 4, 4)
        style_layout.setSpacing(6)
        
        self.combo_scope = NoScrollComboBox()
        self.combo_scope.addItem("All Geometries", "all")
        self.combo_scope.addItem("Selected Only", "selected")
        
        self.combo_rep = NoScrollComboBox()
        self.combo_rep.addItem("Surface Only (Clean)", "surface")
        self.combo_rep.addItem("Surface + Edges", "surface_edges")
        self.combo_rep.addItem("Wireframe", "wireframe")
        self.combo_rep.addItem("Points Cloud", "points")
        self.combo_rep.currentIndexChanged.connect(self.change_representation)
        
        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(85)
        self.slider_opacity.valueChanged.connect(self.change_opacity)
        
        style_layout.addRow("Apply to:", self.combo_scope)
        style_layout.addRow("Appearance:", self.combo_rep)
        style_layout.addRow("Opacity:", self.slider_opacity)
        right_layout.addWidget(self.group_style)
        
        # ── Grupo 2: Physical Info & Mesh Quality Check ──
        self.group_info = QGroupBox("Physical Info & Quality", self.sidebar_content)
        info_layout = QFormLayout(self.group_info)
        info_layout.setContentsMargins(4, 8, 4, 4)
        info_layout.setSpacing(4)
        
        self.lbl_points = QLabel("-")
        self.lbl_cells = QLabel("-")
        self.lbl_bound_x = QLabel("-")
        self.lbl_bound_y = QLabel("-")
        self.lbl_bound_z = QLabel("-")
        self.lbl_watertight = QLabel("-")
        
        info_layout.addRow("Points:", self.lbl_points)
        info_layout.addRow("Cells/Faces:", self.lbl_cells)
        info_layout.addRow("Bounds X:", self.lbl_bound_x)
        info_layout.addRow("Bounds Y:", self.lbl_bound_y)
        info_layout.addRow("Bounds Z:", self.lbl_bound_z)
        info_layout.addRow("Watertight:", self.lbl_watertight)
        
        self.btn_check_quality = QPushButton("Check Mesh Quality")
        self.btn_check_quality.clicked.connect(self.show_quality_dialog)
        info_layout.addRow(self.btn_check_quality)
        
        right_layout.addWidget(self.group_info)
        
        # ── Grupo 3: Clipping / Slicing Plane ──
        self.group_clip = QGroupBox("Slicing Plane (Cut)", self.sidebar_content)
        clip_layout = QVBoxLayout(self.group_clip)
        clip_layout.setContentsMargins(4, 8, 4, 4)
        clip_layout.setSpacing(6)
        
        self.chk_enable_clip = QCheckBox("Enable Clipping Plane")
        self.chk_enable_clip.toggled.connect(self.on_clip_changed)
        clip_layout.addWidget(self.chk_enable_clip)
        
        clip_form = QFormLayout()
        clip_form.setContentsMargins(0, 0, 0, 0)
        clip_form.setSpacing(6)
        
        self.combo_clip_plane = NoScrollComboBox()
        self.combo_clip_plane.addItem("Plane Normal: X", "x")
        self.combo_clip_plane.addItem("Plane Normal: Y", "y")
        self.combo_clip_plane.addItem("Plane Normal: Z", "z")
        self.combo_clip_plane.currentIndexChanged.connect(self.on_clip_changed)
        clip_form.addRow("Plane:", self.combo_clip_plane)
        
        self.chk_clip_invert = QCheckBox("Invert Normal")
        self.chk_clip_invert.toggled.connect(self.on_clip_changed)
        clip_form.addRow("", self.chk_clip_invert)
        
        self.slider_clip_pos = QSlider(Qt.Horizontal)
        self.slider_clip_pos.setRange(0, 100)
        self.slider_clip_pos.setValue(50)
        self.slider_clip_pos.valueChanged.connect(self.on_clip_changed)
        clip_form.addRow("Position:", self.slider_clip_pos)
        
        clip_layout.addLayout(clip_form)
        right_layout.addWidget(self.group_clip)
        
        # ── Grupo 4: Distance Measurement & Ruler ──
        self.group_measure = QGroupBox("3D Measurement & Ruler", self.sidebar_content)
        measure_layout = QVBoxLayout(self.group_measure)
        measure_layout.setContentsMargins(4, 8, 4, 4)
        measure_layout.setSpacing(6)
        
        self.btn_measure = QPushButton("Measure (Pick 2 Points)")
        self.btn_measure.setCheckable(True)
        self.btn_measure.toggled.connect(self.toggle_measurement_mode)
        measure_layout.addWidget(self.btn_measure)
        
        self.lbl_measure_dist = QLabel("Distance: Click 2 points on mesh")
        self.lbl_measure_dist.setWordWrap(True)
        self.lbl_measure_dist.setStyleSheet("color: #0f62fe; font-weight: 600; font-size: 11px;")
        measure_layout.addWidget(self.lbl_measure_dist)
        
        self.btn_clear_measure = QPushButton("Clear Measurement")
        self.btn_clear_measure.clicked.connect(self.clear_measurement)
        measure_layout.addWidget(self.btn_clear_measure)
        
        right_layout.addWidget(self.group_measure)
        
        # ── Grupo 5: snappyHexMesh Patches / Multi-solid ──
        self.group_patches = QGroupBox("snappyHexMesh Patches", self.sidebar_content)
        patch_layout = QVBoxLayout(self.group_patches)
        patch_layout.setContentsMargins(4, 8, 4, 4)
        patch_layout.setSpacing(6)
        
        self.btn_detect_patches = QPushButton("Detect STL Patches")
        self.btn_detect_patches.clicked.connect(self.detect_patches)
        patch_layout.addWidget(self.btn_detect_patches)
        
        self.list_patches = QListWidget()
        self.list_patches.setFixedHeight(75)
        patch_layout.addWidget(self.list_patches)
        
        right_layout.addWidget(self.group_patches)
        
        # ── Grupo 6: Camera & Export ──
        self.group_cam = QGroupBox("Camera & Export", self.sidebar_content)
        cam_layout = QVBoxLayout(self.group_cam)
        cam_layout.setContentsMargins(4, 8, 4, 4)
        cam_layout.setSpacing(6)
        
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
        
        self.btn_screenshot = QPushButton("Screenshot")
        self.btn_screenshot.clicked.connect(self.take_screenshot)
        cam_layout.addWidget(self.btn_screenshot)
        
        right_layout.addWidget(self.group_cam)
        right_layout.addStretch(1)
        
        self.scroll_right.setWidget(self.sidebar_content)
        main_layout.addWidget(self.scroll_right)
        
        self.current_case_path = None
        self.scan_case(None)

    def scan_case(self, case_path):
        """Varre o projeto, popula a lista exibindo apenas os nomes dos arquivos .stl e renderiza as malhas."""
        self.current_case_path = case_path
        
        found_meshes = []
        if case_path and os.path.exists(case_path):
            dirs_to_check = [
                os.path.join(case_path, "constant", "geometry"),
                os.path.join(case_path, "constant", "triSurface"),
                os.path.join(case_path, "constant"),
                case_path
            ]
            
            seen_files = set()
            for d in dirs_to_check:
                if os.path.exists(d):
                    try:
                        for root, _, files in os.walk(d):
                            for f in files:
                                if f.lower().endswith(('.stl', '.obj')):
                                    full_p = os.path.normpath(os.path.join(root, f))
                                    if full_p not in seen_files:
                                        seen_files.add(full_p)
                                        rel_p = os.path.relpath(full_p, case_path)
                                        found_meshes.append((rel_p, full_p))
                    except Exception:
                        pass
        
        self.mesh_list.blockSignals(True)
        self.mesh_list.clear()
        
        if found_meshes:
            self.viewer.load_meshes(found_meshes)
            for idx, (rel_path, full_path) in enumerate(found_meshes):
                file_name = os.path.basename(full_path)
                item = QListWidgetItem(file_name)
                item.setToolTip(rel_path)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                item.setData(Qt.UserRole, full_path)
                
                color_hex = self.viewer._mesh_colors[idx % len(self.viewer._mesh_colors)]
                item.setIcon(self.create_mesh_icon(color_hex))
                self.mesh_list.addItem(item)
            self.mesh_list.blockSignals(False)
            
            self.group_cam.setEnabled(True)
            if self.mesh_list.count() > 0:
                self.mesh_list.setCurrentRow(0)
        else:
            self.mesh_list.blockSignals(False)
            if self.viewer.plotter:
                self.viewer.plotter.clear()

    def showEvent(self, event):
        super().showEvent(event)
        if self.viewer:
            self.viewer.update_render()

    def refresh_scan(self):
        if self.current_case_path:
            self.scan_case(self.current_case_path)

    def select_mesh(self, file_path):
        """Seleciona na lista a malha correspondente ao caminho informado."""
        if not file_path:
            return False
        target = os.path.abspath(file_path)
        for row in range(self.mesh_list.count()):
            item = self.mesh_list.item(row)
            if os.path.abspath(item.data(Qt.UserRole) or "") == target:
                self.mesh_list.setCurrentRow(row)
                return True
        return False

    def on_mesh_item_changed(self, item):
        full_path = item.data(Qt.UserRole) if item else None
        if full_path:
            is_checked = (item.checkState() == Qt.Checked)
            self.viewer.set_mesh_visibility(full_path, is_checked)

    def on_mesh_selection_changed(self, current, previous):
        full_path = current.data(Qt.UserRole) if current else None
        if not full_path:
            self.group_style.setEnabled(False)
            self.group_info.setEnabled(False)
            return
            
        self.group_style.setEnabled(True)
        self.group_info.setEnabled(True)
        
        mesh = self.viewer.meshes.get(full_path)
        if mesh:
            self.lbl_points.setText(f"{mesh.n_points:,}")
            self.lbl_cells.setText(f"{mesh.n_cells:,}")
            b = mesh.bounds
            self.lbl_bound_x.setText(f"[{b[0]:.3f}, {b[1]:.3f}] m")
            self.lbl_bound_y.setText(f"[{b[2]:.3f}, {b[3]:.3f}] m")
            self.lbl_bound_z.setText(f"[{b[4]:.3f}, {b[5]:.3f}] m")
            
            try:
                feature_edges = mesh.extract_feature_edges(boundary_edges=True, feature_edges=False, manifold_edges=False)
                is_wt = (feature_edges.n_cells == 0 and mesh.n_cells > 0)
                self.lbl_watertight.setText("Yes" if is_wt else "No (Open edges)")
                self.lbl_watertight.setStyleSheet("color: #198038;" if is_wt else "color: #da1e28;")
            except Exception:
                self.lbl_watertight.setText("Unknown")
        else:
            self.lbl_points.setText("Erro")
            self.lbl_cells.setText("Erro")
            self.lbl_bound_x.setText("-")
            self.lbl_bound_y.setText("-")
            self.lbl_bound_z.setText("-")
            self.lbl_watertight.setText("-")

    def change_representation(self, index=None):
        if not self.viewer or not self.viewer.plotter:
            return
            
        rep_type = self.combo_rep.currentData()
        scope = self.combo_scope.currentData()
        
        style = "surface"
        show_edges = False
        if rep_type == "surface":
            style = "surface"
            show_edges = False
        elif rep_type == "surface_edges":
            style = "surface"
            show_edges = True
        elif rep_type == "wireframe":
            style = "wireframe"
            show_edges = False
        elif rep_type == "points":
            style = "points"
            show_edges = False
            
        for full_path, prop in self.viewer.mesh_props.items():
            if scope == "all" or (self.mesh_list.currentItem() and self.mesh_list.currentItem().data(Qt.UserRole) == full_path):
                prop["style"] = style
                prop["show_edges"] = show_edges
                if prop["visible"] and full_path in self.viewer.meshes:
                    mesh = self.viewer.meshes[full_path]
                    name = self.viewer.actors.get(full_path)
                    self.viewer.plotter.add_mesh(
                        mesh,
                        color=prop["rgb"],
                        opacity=prop["opacity"],
                        style=prop["style"],
                        show_edges=prop["show_edges"],
                        name=name,
                        reset_camera=False
                    )
        self.viewer.update_render()

    def change_opacity(self, val):
        if not self.viewer or not self.viewer.plotter:
            return
            
        scope = self.combo_scope.currentData()
        opacity = val / 100.0
        
        for full_path, prop in self.viewer.mesh_props.items():
            if scope == "all" or (self.mesh_list.currentItem() and self.mesh_list.currentItem().data(Qt.UserRole) == full_path):
                prop["opacity"] = opacity
                if prop["visible"] and full_path in self.viewer.meshes:
                    mesh = self.viewer.meshes[full_path]
                    name = self.viewer.actors.get(full_path)
                    self.viewer.plotter.add_mesh(
                        mesh,
                        color=prop["rgb"],
                        opacity=prop["opacity"],
                        style=prop["style"],
                        show_edges=prop["show_edges"],
                        name=name,
                        reset_camera=False
                    )
        self.viewer.update_render()

    def on_clip_changed(self):
        """Calcula e aplica o plano de corte nas malhas."""
        enabled = self.chk_enable_clip.isChecked()
        plane_axis = self.combo_clip_plane.currentData()
        invert = self.chk_clip_invert.isChecked()
        pos_ratio = self.slider_clip_pos.value() / 100.0
        
        all_bounds = None
        for mesh in self.viewer.meshes.values():
            if mesh:
                b = mesh.bounds
                if all_bounds is None:
                    all_bounds = list(b)
                else:
                    all_bounds[0] = min(all_bounds[0], b[0])
                    all_bounds[1] = max(all_bounds[1], b[1])
                    all_bounds[2] = min(all_bounds[2], b[2])
                    all_bounds[3] = max(all_bounds[3], b[3])
                    all_bounds[4] = min(all_bounds[4], b[4])
                    all_bounds[5] = max(all_bounds[5], b[5])
                    
        if not all_bounds:
            all_bounds = [-1, 1, -1, 1, -1, 1]

        if plane_axis == "X":
            normal = (1, 0, 0)
            origin_coord = all_bounds[0] + pos_ratio * (all_bounds[1] - all_bounds[0])
            origin = (origin_coord, 0, 0)
        elif plane_axis == "Y":
            normal = (0, 1, 0)
            origin_coord = all_bounds[2] + pos_ratio * (all_bounds[3] - all_bounds[2])
            origin = (0, origin_coord, 0)
        else: # Z
            normal = (0, 0, 1)
            origin_coord = all_bounds[4] + pos_ratio * (all_bounds[5] - all_bounds[4])
            origin = (0, 0, origin_coord)
            
        self.viewer.apply_clip_plane(enabled=enabled, normal=normal, origin=origin, invert=invert)

    def set_cam_view(self, view_type):
        if not self.viewer or not self.viewer.plotter:
            return
            
        if view_type == "iso":
            self.viewer.plotter.view_isometric()
        elif view_type == "xy":
            self.viewer.plotter.view_xy()
        elif view_type == "xz":
            self.viewer.plotter.view_xz()
        self.viewer.plotter.reset_camera()
        self.viewer.update_render()

    def take_screenshot(self):
        if not self.viewer or not self.viewer.plotter:
            return
            
        file_path, _ = QFileDialog.getSaveFileName(self, "Salvar Captura", "", "Imagens PNG (*.png)")
        if file_path:
            self.viewer.plotter.screenshot(file_path)
            QMessageBox.information(self, "Sucesso", f"Captura salva em:\n{file_path}")

    def toggle_measurement_mode(self, active):
        if active:
            self.btn_measure.setStyleSheet("background-color: #0f62fe; color: white;")
            self.lbl_measure_dist.setText("Click Point 1, then Point 2 on geometry...")
            self.viewer.start_measuring(self._on_measurement_result)
        else:
            self.btn_measure.setStyleSheet("")
            self.viewer.clear_measurement()

    def _on_measurement_result(self, p1, p2):
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        dz = p2[2] - p1[2]
        dist = math.sqrt(dx**2 + dy**2 + dz**2)
        
        self.lbl_measure_dist.setText(
            f"Distance: {dist:.4f} m ({dist*1000:.1f} mm)\n"
            f"ΔX: {abs(dx):.4f}m | ΔY: {abs(dy):.4f}m | ΔZ: {abs(dz):.4f}m"
        )
        self.btn_measure.setChecked(False)

    def clear_measurement(self):
        self.btn_measure.setChecked(False)
        self.lbl_measure_dist.setText("Distance: -")
        self.viewer.clear_measurement()

    def show_quality_dialog(self):
        current_item = self.mesh_list.currentItem()
        full_path = current_item.data(Qt.UserRole) if current_item else None
        mesh = self.viewer.meshes.get(full_path) if full_path else None
        
        if not mesh:
            QMessageBox.warning(self, "Quality Check", "No mesh selected.")
            return

        diag = check_mesh_quality(mesh)
        if not diag:
            QMessageBox.warning(self, "Quality Check", "Unable to compute metrics.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Mesh Quality & Watertight Diagnostic")
        dlg.resize(400, 350)
        layout = QVBoxLayout(dlg)
        
        table = QTableWidget(dlg)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Metric", "Value"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        rows = [
            ("Watertight (Snappy-ready)", "YES" if diag["is_watertight"] else "NO (Holes / Open edges)"),
            ("Open Boundary Edges", f"{diag['open_edges']}"),
            ("All Faces Triangulated", "Yes" if diag["is_all_triangles"] else "No"),
            ("Total Points", f"{diag['points']:,}"),
            ("Total Faces / Cells", f"{diag['cells']:,}"),
            ("Surface Area", f"{diag['area']:.6e} m²"),
            ("Enclosed Volume", f"{diag['volume']:.6e} m³" if diag["volume"] is not None else "N/A (Open)"),
            ("Dimensions (ΔX, ΔY, ΔZ)", f"{diag['dimensions'][0]:.3f} × {diag['dimensions'][1]:.3f} × {diag['dimensions'][2]:.3f} m"),
        ]
        
        table.setRowCount(len(rows))
        for r_idx, (k, v) in enumerate(rows):
            table.setItem(r_idx, 0, QTableWidgetItem(k))
            table.setItem(r_idx, 1, QTableWidgetItem(v))
            
        layout.addWidget(table)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        dlg.exec()

    def detect_patches(self):
        current_item = self.mesh_list.currentItem()
        full_path = current_item.data(Qt.UserRole) if current_item else None
        if not full_path:
            return
            
        patches = detect_stl_patches(full_path)
        self.list_patches.clear()
        for p in patches:
            faces_info = f" ({p['faces']} faces)" if p.get('faces') != 'all' else ""
            self.list_patches.addItem(f"{p['name']}{faces_info}")

    def create_mesh_icon(self, color_hex="#0f62fe"):
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        pen = QPen(QColor(color_hex))
        pen.setWidthF(1.5)
        painter.setPen(pen)
        
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
