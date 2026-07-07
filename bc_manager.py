import os
import re
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
                             QPushButton, QLabel, QTableWidget, QTableWidgetItem, 
                             QMessageBox, QHeaderView)
from PySide6.QtCore import Qt

class BCManagerWidget(QWidget):
    """Gerenciador interativo de Condições de Contorno (Boundary Conditions) para arquivos em 0/."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        
        # Barra superior de seleção de arquivo do diretório 0/
        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Campo (0/):"))
        
        self.combo_fields = QComboBox()
        self.combo_fields.currentIndexChanged.connect(self.load_field_file)
        top_layout.addWidget(self.combo_fields, 1)
        
        self.btn_refresh = QPushButton("Atualizar")
        self.btn_refresh.clicked.connect(self.scan_zero_dir)
        top_layout.addWidget(self.btn_refresh)
        
        layout.addLayout(top_layout)
        
        # Tabela de Condições de Contorno
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Fronteira (Patch)", "Tipo (BC Type)", "Valor (Value)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(
            "QTableWidget { gridline-color: #dee2e6; }"
            "QHeaderView::section { background-color: #f1f3f5; font-weight: bold; border: 1px solid #dee2e6; padding: 4px; }"
        )
        layout.addWidget(self.table)
        
        # Botão inferior de salvar
        self.btn_save = QPushButton("Salvar Alterações")
        self.btn_save.setStyleSheet(
            "background-color: #1a73e8; color: white; font-weight: bold; padding: 6px 12px; border-radius: 4px;"
        )
        self.btn_save.clicked.connect(self.save_field_file)
        layout.addWidget(self.btn_save)
        
        self.current_case_path = None
        self.current_file_path = None
        self.active_patches = []
        
        self.scan_zero_dir()

    def scan_zero_dir(self):
        """Escaneia a pasta 0/ do caso ativo e preenche a combobox de campos."""
        if hasattr(self.main_window, 'current_case'):
            self.current_case_path = self.main_window.current_case
            
        self.combo_fields.blockSignals(True)
        self.combo_fields.clear()
        
        if not self.current_case_path:
            self.table.setRowCount(0)
            self.btn_save.setEnabled(False)
            self.combo_fields.blockSignals(False)
            return
            
        zero_dir = os.path.join(self.current_case_path, "0")
        if not os.path.isdir(zero_dir):
            self.table.setRowCount(0)
            self.btn_save.setEnabled(False)
            self.combo_fields.blockSignals(False)
            return
            
        # Lista arquivos comuns de propriedades físicas
        files = []
        try:
            for f in os.listdir(zero_dir):
                full = os.path.join(zero_dir, f)
                if os.path.isfile(full) and not f.startswith('.'):
                    files.append(f)
        except Exception:
            pass
            
        files.sort()
        for f in files:
            self.combo_fields.addItem(f, os.path.join(zero_dir, f))
            
        self.combo_fields.blockSignals(False)
        self.btn_save.setEnabled(True)
        
        if files:
            self.load_field_file()

    def load_field_file(self):
        """Carrega e analisa o arquivo de campo selecionado."""
        file_path = self.combo_fields.currentData()
        self.current_file_path = file_path
        self.table.setRowCount(0)
        self.active_patches = []
        
        if not file_path or not os.path.isfile(file_path):
            return
            
        self.active_patches = self.parse_boundary_field(file_path)
        
        self.table.setRowCount(len(self.active_patches))
        for idx, patch in enumerate(self.active_patches):
            # Patch name (Read-only)
            item_name = QTableWidgetItem(patch['patch'])
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(idx, 0, item_name)
            
            # BC Type (combobox interativa com opções populares)
            combo_type = QComboBox()
            combo_type.setEditable(True)
            combo_type.addItems(["fixedValue", "zeroGradient", "noSlip", "calculated", "inletOutlet", "fixedFluxPressure"])
            combo_type.setCurrentText(patch['type'])
            self.table.setCellWidget(idx, 1, combo_type)
            
            # Value (Text edit)
            item_val = QTableWidgetItem(patch['value'])
            self.table.setItem(idx, 2, item_val)

    def parse_boundary_field(self, file_path):
        """Parser robusto baseado em brace matching para ler o bloco boundaryField."""
        if not os.path.isfile(file_path):
            return []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            return []

        match = re.search(r'boundaryField\s*\{', content)
        if not match:
            return []
        
        start_idx = match.end()
        brace_count = 1
        end_idx = -1
        for idx in range(start_idx, len(content)):
            char = content[idx]
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = idx
                    break
        if end_idx == -1:
            return []
        
        block = content[start_idx:end_idx]
        
        # Encontra patches do bloco
        patches = []
        pattern = re.compile(r'([a-zA-Z0-9_\-\.\:\*]+)\s*\{')
        for m in pattern.finditer(block):
            patch_name = m.group(1)
            # Ignora palavras-chave internas se houver
            if patch_name in ("type", "value"):
                continue
                
            p_start = m.end()
            p_brace = 1
            p_end = -1
            for p_idx in range(p_start, len(block)):
                c = block[p_idx]
                if c == '{':
                    p_brace += 1
                elif c == '}':
                    p_brace -= 1
                    if p_brace == 0:
                        p_end = p_idx
                        break
            if p_end != -1:
                patch_block = block[p_start:p_end]
                
                type_match = re.search(r'type\s+([a-zA-Z0-9_\-\.]+)\s*;', patch_block)
                bc_type = type_match.group(1) if type_match else "calculated"
                
                value_match = re.search(r'value\s+([^;]+);', patch_block)
                bc_val = value_match.group(1).strip() if value_match else ""
                
                patches.append({
                    'patch': patch_name,
                    'type': bc_type,
                    'value': bc_val
                })
        return patches

    def save_field_file(self):
        """Reconstrói e salva o bloco boundaryField com as edições feitas na tabela."""
        if not self.current_file_path or not os.path.isfile(self.current_file_path):
            return
            
        # Lê valores da tabela
        updated_patches = []
        for row in range(self.table.rowCount()):
            patch_name = self.table.item(row, 0).text()
            
            # Recupera o tipo BC da combobox
            widget_type = self.table.cellWidget(row, 1)
            bc_type = widget_type.currentText() if widget_type else "calculated"
            
            # Valor do campo de texto
            item_val = self.table.item(row, 2)
            bc_val = item_val.text().strip() if item_val else ""
            
            updated_patches.append({
                'patch': patch_name,
                'type': bc_type,
                'value': bc_val
            })
            
        try:
            with open(self.current_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível ler o arquivo:\n{e}")
            return

        match = re.search(r'boundaryField\s*\{', content)
        if not match:
            QMessageBox.critical(self, "Erro", "Bloco 'boundaryField' não encontrado no arquivo.")
            return
            
        start_idx = match.start()
        brace_count = 1
        end_idx = -1
        for idx in range(match.end(), len(content)):
            char = content[idx]
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = idx + 1
                    break
        if end_idx == -1:
            QMessageBox.critical(self, "Erro", "Erro ao parsear fechamento de 'boundaryField'.")
            return
            
        # Reconstroi o bloco boundaryField preservando a identação padrão
        new_block = "boundaryField\n{\n"
        for p in updated_patches:
            new_block += f"    {p['patch']}\n    {{\n"
            new_block += f"        type            {p['type']};\n"
            if p['value']:
                new_block += f"        value           {p['value']};\n"
            new_block += "    }\n"
        new_block += "}"
        
        new_content = content[:start_idx] + new_block + content[end_idx:]
        
        try:
            with open(self.current_file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            # Força recarga no editor se o arquivo correspondente estiver aberto
            if hasattr(self.main_window, 'path_to_editor'):
                editor = self.main_window.path_to_editor.get(self.current_file_path)
                if editor:
                    editor.blockSignals(True)
                    editor.setPlainText(new_content)
                    editor.blockSignals(False)
                    
            QMessageBox.information(self, "Sucesso", "Condições de contorno salvas com sucesso!")
            if hasattr(self.main_window, 'log'):
                self.main_window.log(f"BC salvas com sucesso em: {self.current_file_path}\n")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao salvar arquivo:\n{e}")
