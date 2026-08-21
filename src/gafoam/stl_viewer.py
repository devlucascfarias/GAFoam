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
    QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QPen, QColor, QPixmap, QIcon, QFont


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
        
        try:
            self.plotter = QtInteractor(self)
            self.layout.addWidget(self.plotter.interactor)
            self.plotter.set_background("white")
        except Exception as e:
            self.layout.addWidget(QLabel(f"Erro ao inicializar visualizador 3D: {e}"))
            self.plotter = None
            
        self.actors = {}
        self.meshes = {} # Armazena os objetos pyvista.PolyData originais
        
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
        self.measurement_actor = None
        self.clip_active = False

    def load_meshes(self, files_list):
        """Carrega e renderiza simultaneamente todas as malhas listadas com cores distintas e superfícies lisas."""
        if not self.plotter:
            return
            
        self.plotter.clear()
        self.actors = {}
        self.meshes = {}
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

                    actor = self.plotter.add_mesh(
                        mesh,
                        color=rgb,
                        show_edges=False,
                        edge_color="#161616",
                        opacity=mesh_opacity,
                        name=rel_path,
                        scalars=None,
                        reset_camera=False
                    )
                    if actor and hasattr(actor, 'GetProperty'):
                        prop = actor.GetProperty()
                        prop.SetColor(rgb[0], rgb[1], rgb[2])
                        prop.SetDiffuseColor(rgb[0], rgb[1], rgb[2])
                        prop.SetAmbientColor(rgb[0] * 0.2, rgb[1] * 0.2, rgb[2] * 0.2)
                        prop.SetOpacity(mesh_opacity)
                        prop.SetRepresentationToSurface()
                        prop.SetEdgeVisibility(False)
                        
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

    def apply_clip_plane(self, enabled=False, normal=(1, 0, 0), origin=(0, 0, 0), invert=False):
        """Aplica plano de corte dinâmico a todas as malhas ativas."""
        if not self.plotter:
            return
            
        self.clip_active = enabled
        if not enabled:
            for full_path, mesh in self.meshes.items():
                actor = self.actors.get(full_path)
                if actor and hasattr(actor, 'GetMapper'):
                    actor.GetMapper().SetInputData(mesh)
            self.plotter.render()
            return

        norm = [-normal[0], -normal[1], -normal[2]] if invert else list(normal)
        for full_path, mesh in self.meshes.items():
            try:
                clipped = mesh.clip(normal=norm, origin=origin, invert=False)
                actor = self.actors.get(full_path)
                if actor and hasattr(actor, 'GetMapper'):
                    if clipped.n_points > 0:
                        actor.GetMapper().SetInputData(clipped)
            except Exception:
                pass
        self.plotter.render()

    def start_measuring(self, callback=None):
        """Ativa a ferramenta de medição interativa por pontos."""
        self.measurement_points = []
        self.on_measure_callback = callback
        if self.plotter:
            try:
                self.plotter.enable_point_picking(
                    callback=self._on_point_picked, 
                    show_message=False, 
                    color="#0f62fe", 
                    point_size=10
                )
            except Exception:
                pass

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
                self.plotter.add_mesh(line, color="#da1e28", line_width=3, name="__measurement_line__")
                self.plotter.render()
            except Exception:
                pass
                
            if self.on_measure_callback:
                self.on_measure_callback(p1, p2)
            self.measurement_points = []

    def clear_measurement(self):
        """Limpa as marcações e desativa a ferramenta de medição."""
        self.measurement_points = []
        if self.plotter:
            try:
                self.plotter.remove_actor("__measurement_line__")
            except Exception:
                pass
            try:
                self.plotter.disable_picking()
            except Exception:
                pass
            self.plotter.render()

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
        
        if scope == "all":
            actors = list(self.viewer.actors.values())
        else:
            current_item = self.mesh_list.currentItem()
            full_path = current_item.data(Qt.UserRole) if current_item else None
            act = self.viewer.actors.get(full_path) if full_path else None
            actors = [act] if act else []
        
        for actor in actors:
            if not actor or not hasattr(actor, 'GetProperty'):
                continue
            prop = actor.GetProperty()
            if rep_type == "surface":
                prop.SetRepresentationToSurface()
                prop.SetEdgeVisibility(False)
            elif rep_type == "surface_edges":
                prop.SetRepresentationToSurface()
                prop.SetEdgeVisibility(True)
            elif rep_type == "wireframe":
                prop.SetRepresentationToWireframe()
                prop.SetEdgeVisibility(False)
            elif rep_type == "points":
                prop.SetRepresentationToPoints()
                prop.SetEdgeVisibility(False)
                
        self.viewer.plotter.render()

    def change_opacity(self, val):
        if not self.viewer or not self.viewer.plotter:
            return
            
        scope = self.combo_scope.currentData()
        opacity = val / 100.0
        
        if scope == "all":
            actors = list(self.viewer.actors.values())
        else:
            current_item = self.mesh_list.currentItem()
            full_path = current_item.data(Qt.UserRole) if current_item else None
            act = self.viewer.actors.get(full_path) if full_path else None
            actors = [act] if act else []
            
        for actor in actors:
            if actor and hasattr(actor, 'GetProperty'):
                actor.GetProperty().SetOpacity(opacity)
                
        self.viewer.plotter.render()

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

    def set_cam_view(self, view):
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
        if not self.viewer.plotter or not self.current_case_path:
            return
            
        timestamp = int(time.time())
        default_name = f"screenshot_geometria_{timestamp}.png"
        
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
