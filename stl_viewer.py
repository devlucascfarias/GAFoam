import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtWidgets import QWidget, QVBoxLayout

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
                        # Cada 3 vértices formam uma face triangular
                        n_faces = len(vertices) // 3
                        if n_faces > 0:
                            # Formato PyVista para faces: [3, v1, v2, v3, 3, v4, v5, v6, ...]
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
                import os
                QMessageBox.warning(self, "Aviso", f"O arquivo '{os.path.basename(file_path)}' não pôde ser interpretado como um STL válido (pode estar vazio ou corrompido).")
                
        except Exception as e:
            print(f"Erro ao carregar STL: {e}")

    def closeEvent(self, event):
        if self.plotter:
            self.plotter.close()
        super().closeEvent(event)
