import os
import sys
import re
import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import (QApplication, QWidget, QWidgetAction, QPushButton, QVBoxLayout, QHBoxLayout, 
                             QFileDialog, QTextEdit, QLabel, QMenuBar, QMenu, QAction, 
                             QLineEdit, QStatusBar, QTreeView, QComboBox, QDialog, QTableWidget, QTableWidgetItem, QMessageBox, QInputDialog)
from PyQt5.QtCore import QTimer, QProcess, Qt, QDir, QFileInfo, QProcessEnvironment
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon
from PyQt5 import QtCore

from rate_calculator import calculate_increase_rate
from syntax_highlighter import OpenFOAMHighlighter
from simulation_history import SimulationHistory
from datetime import datetime
import json

class OpenFOAMInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GAFoam")
        self.resize(1000, 600)

        # Carregar configurações
        self.config_file = "config.json"
        self.config = self.load_config()

        # Caminhos parametrizados
        self.baseDir = self.config.get("baseDir", os.getcwd())
        self.systemDir = os.path.join(self.baseDir, "system")
        self.unvFilePath = ""
        self.currentFilePath = ""
        self.currentOpenFOAMVersion = self.config.get("openFOAMVersion", "openfoam9")
        self.currentSolver = self.config.get("solver", "twoLiquidMixingFoam")
        self.currentProcess = None
        
        # Dados para gráfico de resíduos

        self.residualData = {}
        self.timeData = []
        self.residualLines = {}
        self.colors = ['r', 'g', 'b', 'c', 'm', 'y', 'w'] 
        
        self.mainVerticalLayout = QVBoxLayout(self)
        self.mainVerticalLayout.setContentsMargins(5, 5, 5, 5)
        
        self.setupMenuBar()
        self.setupMainContentArea()
        self.setupStatusBar()
        
        self.systemMonitorTimer = QTimer(self)
        self.systemMonitorTimer.timeout.connect(self.updateSystemUsage)
        self.systemMonitorTimer.start(2000)
        
        self.setLayout(self.mainVerticalLayout)
        self.simulationHistory = SimulationHistory()
    
    def detectOpenFOAMVersions(self):
        versions = []
        openfoamDir = QDir("/opt")
        
        filters = ["openfoam*", "OpenFOAM*"]
        for dirName in openfoamDir.entryList(filters, QDir.Dirs | QDir.NoDotAndDotDot):
            versions.append(dirName)
        
        if not versions:
            versions.append("openfoam9")
            print("Warning: Nenhuma versão do OpenFOAM encontrada em /opt. Usando fallback.")
        
        return versions
    
    def clearOldProcessorDirs(self):
        caseDir = QDir("/home/gaf/build-GAFoam-Desktop-Debug")
        
        processorDirs = caseDir.entryList(["processor*"], QDir.Dirs | QDir.NoDotAndDotDot)
        for dirName in processorDirs:
            processorDir = QDir(caseDir.filePath(dirName))
            if processorDir.removeRecursively():
                self.outputArea.append(f"Removendo pasta antiga: {dirName}")

    def chooseUNV(self):
        unvFilePath, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher Arquivo .unv",
            "",
            "Arquivos UNV (*.unv)"
        )
        
        if unvFilePath:
            self.unvFilePath = unvFilePath
            self.outputArea.append(f"Arquivo .unv carregado: {unvFilePath}")
            self.meshPathLabel.setText(f"Malha: {QFileInfo(unvFilePath).fileName()}")
        else:
            self.outputArea.append("Nenhum arquivo .unv foi selecionado.")    
    
    def chooseCase(self):
        casePath = QFileDialog.getExistingDirectory(
            self, 
            "Escolher Pasta do Caso", 
            "", 
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if casePath:
            # Verifica se a pasta contém os diretórios necessários
            required_dirs = ["0", "system", "constant"]
            if all(QDir(casePath).exists(dir_name) for dir_name in required_dirs):
                self.unvFilePath = casePath  # Atualiza o caminho do caso
                self.outputArea.append(f"Pasta do caso escolhida: {casePath}")
                self.meshPathLabel.setText(f"Malha: {QFileInfo(casePath).fileName()}")
                self.outputArea.append("Caso carregado com sucesso.")
                self.populateTreeView(casePath)  # Atualiza a árvore de diretórios
            else:
                self.outputArea.append("Erro: A pasta selecionada não contém os diretórios necessários (0, system, constant).")
        else:
            self.outputArea.append("Nenhuma pasta foi selecionada.")
    
    # Atualize o menu para refletir a nova funcionalidade
    def setupMenuBar(self):
        self.menuBar = QMenuBar(self)
        
        fileMenu = QMenu("Arquivo", self.menuBar)
        
        refreshTreeAction = QAction("Atualizar Árvore", self)
        refreshTreeAction.triggered.connect(lambda: self.populateTreeView(QFileInfo(self.unvFilePath).absolutePath() if self.unvFilePath else None))
        
        importUNVAction = QAction("Carregar Arquivo .unv", self)
        importUNVAction.triggered.connect(self.chooseUNV)
        
        importCaseAction = QAction("Carregar Caso", self)
        importCaseAction.triggered.connect(self.chooseCase)
        
        fileMenu.addAction(refreshTreeAction)
        fileMenu.addAction(importUNVAction)
        fileMenu.addAction(importCaseAction)
        
        self.menuBar.addMenu(fileMenu)
        self.mainVerticalLayout.setMenuBar(self.menuBar)
        
        terminalMenu = QMenu("Terminal", self.menuBar)
        
        clearTerminalAction = QAction("Limpar Terminal", self)
        clearTerminalAction.triggered.connect(self.clearTerminal)
        
        terminalMenu.addAction(clearTerminalAction)
        
        # Menu OpenFOAM

        openfoamMenu = QMenu("OpenFOAM", self.menuBar)
        
        self.versionComboBox = QComboBox(self)
        self.versionComboBox.addItems(self.detectOpenFOAMVersions())
        self.versionComboBox.setCurrentText(self.currentOpenFOAMVersion)
        self.versionComboBox.currentTextChanged.connect(self.setOpenFOAMVersion)
        
        versionAction = QWidgetAction(openfoamMenu)
        versionAction.setDefaultWidget(self.versionComboBox)
        openfoamMenu.addAction(versionAction)
        
        # Menu Solver

        solverMenu = QMenu("Solver", self.menuBar)
        
        selectSolverAction = QAction("Selecionar Solver...", self)
        selectSolverAction.triggered.connect(self.selectSolver)
        
        solverMenu.addAction(selectSolverAction)
        
        # Adiciona menus à barra de menus

        self.menuBar.addMenu(fileMenu)
        self.menuBar.addMenu(terminalMenu)
        self.menuBar.addMenu(openfoamMenu)
        self.menuBar.addMenu(solverMenu)
        
        historyMenu = QMenu("Histórico", self.menuBar)
        viewHistoryAction = QAction("Ver Histórico de Simulações", self)
        viewHistoryAction.triggered.connect(self.openSimulationHistory)
        historyMenu.addAction(viewHistoryAction)
        self.menuBar.addMenu(historyMenu)
        
        self.mainVerticalLayout.setMenuBar(self.menuBar)

        setBaseDirAction = QAction("Configurar Diretório Base", self)
        setBaseDirAction.triggered.connect(self.set_base_dir)
        fileMenu.addAction(setBaseDirAction)
    
    def setOpenFOAMVersion(self, version):
        self.currentOpenFOAMVersion = version
        self.outputArea.append(f"Versão selecionada: {version}")
    
    def selectSolver(self):
        solverPath = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Pasta do Solver",
            f"/opt/{self.currentOpenFOAMVersion}/applications/solvers"
        )
        
        if solverPath:
            solverName = QFileInfo(solverPath).fileName()
            self.currentSolver = solverName
            self.solverLabel.setText(f"Solver: {solverName}")
            self.outputArea.append(f"Solver selecionado: {solverName}")
            
            # Atualiza o controlDict com o novo solver
            controlDictPath = "/home/gaf/build-GAFoam-Desktop-Debug/system/controlDict"
            try:
                with open(controlDictPath, "r") as file:
                    content = file.read()
                
                # Substitui a linha de solver com expressão regular
                import re
                updated_content = re.sub(
                    r'(solver\s+)([^;]*)(;)',
                    rf'\1{solverName}\3',
                    content
                )
                
                with open(controlDictPath, "w") as file:
                    file.write(updated_content)
                    
                self.outputArea.append(f"Arquivo controlDict atualizado para usar o solver {solverName}.")
                
                # Atualiza a árvore de arquivos para refletir a mudança
                self.populateTreeView(QFileInfo(self.unvFilePath).absolutePath() if self.unvFilePath else None)
                
            except Exception as e:
                self.outputArea.append(f"Erro ao atualizar o controlDict: {str(e)}")
        else:
            self.outputArea.append("Nenhum solver selecionado.")
    
    def setupMainContentArea(self):
        contentLayout = QHBoxLayout()
        
        # Área do terminal (esquerda)
        leftContentLayout = QVBoxLayout()
        terminalLayout = QVBoxLayout()
        terminalLayout.addWidget(QLabel("Terminal e Logs", self))
        
        self.openParaviewButton = QPushButton("Abrir no ParaView", self)
        self.openParaviewButton.clicked.connect(self.openParaview)

        self.calculateRateButton = QPushButton("Calcular Δy", self)
        self.calculateRateButton.clicked.connect(self.openRateCalculationDialog)

        self.fluidPropertiesButton = QPushButton("Calcular Propriedades do Fluido", self)
        self.fluidPropertiesButton.clicked.connect(self.openFluidPropertiesDialog)

        buttonRowLayout = QHBoxLayout()
        buttonRowLayout.addWidget(self.openParaviewButton)
        buttonRowLayout.addWidget(self.calculateRateButton)
        buttonRowLayout.addWidget(self.fluidPropertiesButton)

        # Adicionar botão para configurar núcleos
        self.setCoresButton = QPushButton("Configurar Núcleos para decomposePar", self)
        self.setCoresButton.clicked.connect(self.configureDecomposeParCores)
        buttonRowLayout.addWidget(self.setCoresButton)

        terminalLayout.addLayout(buttonRowLayout)
        
        self.outputArea = QTextEdit(self)
        self.outputArea.setReadOnly(True)
        terminalLayout.addWidget(self.outputArea)
        
        self.terminalInput = QLineEdit(self)
        self.terminalInput.setPlaceholderText(">>")
        self.terminalInput.returnPressed.connect(self.executeTerminalCommand)
        terminalLayout.addWidget(self.terminalInput)
        
        leftContentLayout.addLayout(terminalLayout)
        
        # Gráfico de resíduos
        
        residualLayout = QVBoxLayout()
        residualLayout.addWidget(QLabel("Gráfico de Resíduos", self))
        
        self.graphWidget = pg.PlotWidget()
        self.graphWidget.setBackground('w')
        self.graphWidget.setLabel('left', 'Resíduos')
        self.graphWidget.setLabel('bottom', 'Tempo')
        self.graphWidget.setLogMode(y=True)  
        self.graphWidget.showGrid(x=True, y=True)
        self.graphWidget.addLegend()
        residualLayout.addWidget(self.graphWidget)
        
        graphControlLayout = QHBoxLayout()

        self.clearPlotButton = QPushButton("Limpar Gráfico", self)
        self.clearPlotButton.clicked.connect(self.clearResidualPlot)

        self.exportPlotDataButton = QPushButton("Exportar Dados", self)
        self.exportPlotDataButton.clicked.connect(self.exportPlotData)  

        graphControlLayout.addWidget(self.clearPlotButton)
        graphControlLayout.addWidget(self.exportPlotDataButton)


        residualLayout.addLayout(graphControlLayout)
        
        leftContentLayout.addLayout(residualLayout)
        
        # Área dos botões

        buttonLayout = QVBoxLayout()
        
        self.convertButton = QPushButton("Converter Malha", self)
        self.convertButton.clicked.connect(self.convertMesh)
        buttonLayout.addWidget(self.convertButton)
        
        self.checkMeshButton = QPushButton("Checar Malha", self)
        self.checkMeshButton.clicked.connect(self.checkMesh)
        buttonLayout.addWidget(self.checkMeshButton)
        
        self.decomposeParButton = QPushButton("Decompor Núcleos", self)
        self.decomposeParButton.clicked.connect(self.decomposePar)
        buttonLayout.addWidget(self.decomposeParButton)
        
        self.runButton = QPushButton("Rodar Simulação", self)
        self.runButton.setStyleSheet("background-color: green; color: white; font-weight: bold;")
        self.runButton.clicked.connect(self.runSimulation)
        
        self.stopButton = QPushButton("Parar Simulação", self)
        self.stopButton.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        self.stopButton.clicked.connect(self.stopSimulation)
        
        self.reconstructButton = QPushButton("Reconstruir", self)
        self.reconstructButton.clicked.connect(self.reconstructPar)
        
        self.clearDecomposeButton = QPushButton("Limpar Processadores", self)
        self.clearDecomposeButton.clicked.connect(self.clearDecomposedProcessors)
        
        self.clearSimulationButton = QPushButton("Limpar Arquivos de Simulação", self)
        self.clearSimulationButton.clicked.connect(self.clearSimulation)

        buttonLayout.addWidget(self.convertButton)
        buttonLayout.addWidget(self.decomposeParButton)
        buttonLayout.addWidget(self.runButton)
        buttonLayout.addWidget(self.stopButton)
        buttonLayout.addWidget(self.reconstructButton)
        buttonLayout.addWidget(self.clearDecomposeButton)
        buttonLayout.addWidget(self.clearSimulationButton)
        
        leftContentLayout.addLayout(buttonLayout)
        
        # Área do editor (centro)
        editorLayout = QVBoxLayout()
        editorLayout.addWidget(QLabel("Editor de Arquivo", self))
        
        self.fileEditor = QTextEdit(self)
        self.highlighter = OpenFOAMHighlighter(self.fileEditor.document()) 
        editorLayout.addWidget(self.fileEditor)
        
        self.editButton = QPushButton("Editar Arquivo", self)
        self.editButton.clicked.connect(self.editFile)
        
        self.saveButton = QPushButton("Salvar Arquivo", self)
        self.saveButton.clicked.connect(self.saveFile)
        
        editorLayout.addWidget(self.editButton)
        editorLayout.addWidget(self.saveButton)
        
        # Área de diretórios com barra de pesquisa
        treeLayout = QVBoxLayout()
        treeLayout.addWidget(QLabel("Diretórios", self))
        
        self.searchBar = QLineEdit(self)
        self.searchBar.setPlaceholderText("Pesquisar arquivos...")
        self.searchBar.textChanged.connect(self.filterTreeView)
        treeLayout.addWidget(self.searchBar)
        
        self.treeView = QTreeView(self)
        self.treeModel = QStandardItemModel(self)
        self.treeView.setModel(self.treeModel)
        self.treeView.setHeaderHidden(True)
        self.treeView.doubleClicked.connect(self.onTreeViewDoubleClicked)
        
        treeLayout.addWidget(self.treeView)
        
        contentLayout.addLayout(leftContentLayout, 3)
        contentLayout.addLayout(editorLayout, 1)
        contentLayout.addLayout(treeLayout, 1)
        
        self.mainVerticalLayout.addLayout(contentLayout, 1)

        self.treeUpdateTimer = QTimer(self)
        self.treeUpdateTimer.timeout.connect(lambda: self.populateTreeView())
        self.treeUpdateTimer.start(1000) 

    def toggleLogScale(self):
        """Alterna entre escala linear e logarítmica no eixo Y"""
        current = self.graphWidget.getViewBox().getState()['logMode'][1]
        self.graphWidget.setLogMode(y=not current)
        scale_type = "logarítmica" if not current else "linear"
        self.outputArea.append(f"Escala {scale_type} ativada", 2000)

    def exportPlotData(self):
        """Exporta os dados do gráfico para um arquivo CSV"""
        if not self.timeData:
            self.outputArea.append("Nenhum dado para exportar", 2000)
            return
            
        fileName, _ = QFileDialog.getSaveFileName(
            self, "Salvar dados de resíduos", "", "CSV Files (*.csv)"
        )
        
        if fileName:
            with open(fileName, 'w') as f:
                header = "Time," + ",".join(self.residualData.keys())
                f.write(header + "\n")
                
                for i, time in enumerate(self.timeData):
                    line = f"{time}"
                    for var in self.residualData:
                        if i < len(self.residualData[var]):
                            value = self.residualData[var][i]
                            line += f",{value if value is not None else ''}"
                        else:
                            line += ","
                    f.write(line + "\n")
                    
            self.outputArea.append(f"Dados exportados para {fileName}")
        
    def onTreeViewDoubleClicked(self, index):
        item = self.treeModel.itemFromIndex(index)
        if item and not item.hasChildren():
            filePath = item.data(Qt.UserRole)
            if filePath:
                file = QtCore.QFile(filePath)
                if file.open(QtCore.QIODevice.ReadOnly | QtCore.QIODevice.Text):
                    self.currentFilePath = filePath
                    self.fileEditor.setPlainText(str(file.readAll(), 'utf-8'))
                    file.close()
                    self.outputArea.append(f"Arquivo carregado: {filePath}")
    
    def setupStatusBar(self):
        self.statusBar = QStatusBar(self)
        
        self.meshPathLabel = QLabel("Malha: Nenhuma", self.statusBar)
        self.solverLabel = QLabel(f"Solver: {self.currentSolver}", self.statusBar)
        self.cpuUsageLabel = QLabel("CPU: --%", self.statusBar)
        self.memUsageLabel = QLabel("Memória: --%", self.statusBar)

        self.statusBar.addPermanentWidget(self.solverLabel, 1)
        self.statusBar.addPermanentWidget(self.meshPathLabel, 1)
        self.statusBar.addPermanentWidget(self.cpuUsageLabel)
        self.statusBar.addPermanentWidget(self.memUsageLabel)
        
        self.mainVerticalLayout.addWidget(self.statusBar)
    
    def updateSystemUsage(self):
        try:
            with open('/proc/stat', 'r') as f:
                lines = f.readlines()
                if lines:
                    values = lines[0].split()[1:]
                    if len(values) >= 4:
                        user, nice, system, idle = map(int, values[:4])
                        total = user + nice + system + idle
                        
                        if hasattr(self, 'lastTotal') and hasattr(self, 'lastIdle'):
                            deltaTotal = total - self.lastTotal
                            deltaIdle = idle - self.lastIdle
                            
                            if deltaTotal > 0 and self.lastTotal > 0:
                                cpuUsage = 100 * (deltaTotal - deltaIdle) / deltaTotal
                                self.cpuUsageLabel.setText(f"CPU: {int(cpuUsage)}%")
                        
                        self.lastTotal = total
                        self.lastIdle = idle
        except:
            pass
        
        storage = QtCore.QStorageInfo(QtCore.QDir.rootPath())
        memUsed = (storage.bytesTotal() - storage.bytesFree()) / (1024.0**3)
        memTotal = storage.bytesTotal() / (1024.0**3)
        memPercent = (memUsed / memTotal) * 100 if memTotal > 0 else 0
        
        self.memUsageLabel.setText(
            f"Memória: {int(memPercent)}% ({memUsed:.1f}G/{memTotal:.1f}G)"
        )
    
    def populateTreeView(self, casePath=None):
        """Atualiza a árvore de diretórios com o conteúdo do caso"""
        if not casePath:
            casePath = QFileInfo(self.unvFilePath).absolutePath() if self.unvFilePath else "/home/gaf/build-GAFoam-Desktop-Debug"
        
        self.treeModel = QStandardItemModel(self)
        rootItem = QStandardItem(QIcon.fromTheme("folder"), casePath)
        self.treeModel.appendRow(rootItem)
        self.addDirectoryToTree(casePath, rootItem)
        self.treeView.setModel(self.treeModel)
        self.treeView.expandAll()
    
    def addDirectoryToTree(self, path, parent):
        dir = QDir(path)
        dirName = dir.dirName()
        item = QStandardItem(dirName)
        
        item.setIcon(QIcon.fromTheme("folder"))
        parent.appendRow(item)
        
        filters = QDir.AllEntries | QDir.NoDotAndDotDot
        sorting = QDir.DirsFirst | QDir.Name | QDir.IgnoreCase
        
        for info in dir.entryInfoList(filters, sorting):
            if info.isDir():
                self.addDirectoryToTree(info.absoluteFilePath(), item)
            else:
                fileItem = QStandardItem(info.fileName())
                fileItem.setIcon(QIcon.fromTheme("text-x-generic"))
                item.appendRow(fileItem)
                fileItem.setData(info.absoluteFilePath(), Qt.UserRole)
    
    def openParaview(self):
        if not self.unvFilePath:
            self.outputArea.append("Erro: Nenhum caso selecionado")
            return
        
        caseDir = QFileInfo(self.unvFilePath).absolutePath()
        command = f"paraview --data={caseDir}/foam.foam"
        
        process = QProcess(self)
        process.start(command)
        
        if not process.waitForStarted():
            self.outputArea.append("Erro ao abrir o ParaView")
        else:
            self.outputArea.append("ParaView iniciado com sucesso")
    
    def checkMesh(self):
        if not self.unvFilePath:
            self.outputArea.append("Erro: Nenhum arquivo UNV selecionado")
            return
        
        self.outputArea.append("Executando checkMesh...")
        command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && checkMesh"'
        
        process = QProcess(self)
        self.setupProcessEnvironment(process)
        self.connectProcessSignals(process)
        self.outputArea.append(f"Comando executado: {command}")
        process.start(command)
    
    def convertMesh(self):
        if not self.unvFilePath:
            self.outputArea.append("Erro: Nenhum arquivo UNV selecionado")
            return
        
        self.outputArea.append("Convertendo malha para OpenFOAM...")
        command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && ideasUnvToFoam {self.unvFilePath}"'
        
        process = QProcess(self)
        self.setupProcessEnvironment(process)
        self.connectProcessSignals(process)
        self.outputArea.append(f"Comando executado: {command}")
        process.start(command)
    
    def parseResiduals(self, line):
        """Analisa a saída do terminal para capturar resíduos e tempos."""
        # Captura o tempo atual
        current_time_match = re.search(r'Time = ([0-9.e+-]+)', line)
        if current_time_match:
            current_time = float(current_time_match.group(1))
            if current_time not in self.timeData:
                self.timeData.append(current_time)

        # Captura os resíduos
        residual_match = re.search(r'(?:DILUPBiCGStab|GAMG|diagonal):\s+Solving for ([a-zA-Z0-9_]+), Initial residual = ([0-9.e+-]+)', line)
        if residual_match:
            variable = residual_match.group(1)
            residual = float(residual_match.group(2))

            # Inicializa os dados da variável, se necessário
            if variable not in self.residualData:
                self.residualData[variable] = []
                color_idx = len(self.residualData) % len(self.colors)
                pen = pg.mkPen(color=self.colors[color_idx], width=2)
                self.residualLines[variable] = self.graphWidget.plot(
                    [], [], name=variable, pen=pen, symbolBrush=self.colors[color_idx], 
                    symbolPen='w', symbol='o', symbolSize=5
                )

            # Preenche valores ausentes com None para sincronizar com o tempo
            while len(self.residualData[variable]) < len(self.timeData) - 1:
                self.residualData[variable].append(None)

            # Adiciona o novo resíduo
            self.residualData[variable].append(residual)

            # Garante que os tamanhos sejam iguais
            while len(self.residualData[variable]) > len(self.timeData):
                self.timeData.append(None)

            # Atualiza o gráfico
            self.updateResidualPlot(variable)

    def updateResidualPlot(self, variable):
        """Atualiza o gráfico de resíduos para uma variável específica."""
        if variable in self.residualLines:
            # Filtra os valores None antes de atualizar o gráfico
            filtered_time_data = [t for t, r in zip(self.timeData, self.residualData[variable]) if r is not None]
            filtered_residual_data = [r for r in self.residualData[variable] if r is not None]

            if filtered_time_data and filtered_residual_data:
                self.residualLines[variable].setData(filtered_time_data, filtered_residual_data)
            else:
                self.outputArea.append(f"Dados insuficientes para atualizar o gráfico de {variable}.")

    def clearResidualPlot(self):
        """Limpa o gráfico de resíduos"""
        self.timeData = []
        self.residualData = {}
        self.graphWidget.clear()
        self.residualLines = {}

    def connectProcessSignals(self, process):
        """Conecta os sinais do processo para capturar saída e atualizar resíduos."""
        def readOutput():
            while process.canReadLine():
                output = str(process.readLine(), 'utf-8').strip()
                self.outputArea.append(output)
                self.parseResiduals(output)
                QApplication.processEvents()  # Força a atualização da interface

        def readError():
            error = str(process.readAllStandardError(), 'utf-8').strip()
            self.outputArea.append(error)

        process.readyReadStandardOutput.connect(readOutput)
        process.readyReadStandardError.connect(readError)

    # Atualize o método runSimulation para verificar se o caso é válido
        start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.outputArea.append("Iniciando simulação...")
        
        if not self.unvFilePath:
            self.outputArea.append("Erro: Nenhum caso selecionado")
            return

        # Verifica se é uma pasta de caso válida
        required_dirs = ["0", "system", "constant"]
        if not all(QDir(self.unvFilePath).exists(dir_name) for dir_name in required_dirs):
            self.outputArea.append("Erro: A pasta selecionada não contém os diretórios necessários (0, system, constant).")
            return

        if not self.currentSolver:
            self.outputArea.append("Erro: Nenhum solver selecionado")
            return

        self.clearResidualPlot()

        command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && mpirun -np 6 {self.currentSolver} -parallel"'

        self.outputArea.append(f"Iniciando simulação com {self.currentSolver}...")
        self.currentProcess = QProcess(self)
        self.setupProcessEnvironment(self.currentProcess)

        def finished(code):
            if code == 0:
                self.outputArea.append("Simulação concluída com sucesso.")
            else:
                self.outputArea.append(f"Simulação finalizada com código de erro: {code}")

        self.currentProcess.finished.connect(finished)
        self.connectProcessSignals(self.currentProcess)
        self.outputArea.append(f"Comando executado: {command}")

        self.currentProcess.start("bash", ["-l", "-c", command])
        self.currentProcess.finished.connect(lambda: self.logSimulationCompletion(start_time))

    def logSimulationCompletion(self, start_time):
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status = "Concluído" if self.currentProcess.exitCode() == 0 else "Interrompida"
        self.simulationHistory.add_entry(
            solver=self.currentSolver,
            case_path=self.unvFilePath,
            start_time=start_time,
            end_time=end_time,
            status=status
        )
        self.outputArea.append(f"Simulação {status}.")

    def reconstructPar(self):
        if not self.unvFilePath:
            self.outputArea.append("Erro: Nenhum arquivo UNV selecionado")
            return
        
        self.outputArea.append("Reconstruindo caso...")
        command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && reconstructPar"'
        
        self.currentProcess = QProcess(self)
        self.setupProcessEnvironment(self.currentProcess)
        
        def finished(code):
            self.outputArea.append(f"Reconstrução finalizada com código {code}", 5000)
            self.currentProcess = None
        
        self.currentProcess.finished.connect(finished)
        self.connectProcessSignals(self.currentProcess)
        self.outputArea.append(f"Comando executado: {command}")
        self.currentProcess.start(command)
    
    def decomposePar(self):
        if not self.unvFilePath:
            self.outputArea.append("Erro: Nenhum caso selecionado.")
            return

        # Verifica se a pasta do caso contém os diretórios necessários
        required_dirs = ["0", "system", "constant"]
        if not all(QDir(self.unvFilePath).exists(dir_name) for dir_name in required_dirs):
            self.outputArea.append("Erro: A pasta selecionada não contém os diretórios necessários (0, system, constant).")
            return

        self.outputArea.append("Iniciando decomposição dos núcleos...")
        command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && decomposePar"'

        self.currentProcess = QProcess(self)
        self.setupProcessEnvironment(self.currentProcess)

        # Define a pasta do caso como diretório de trabalho
        self.currentProcess.setWorkingDirectory(self.unvFilePath)

        def finished(code):
            if code == 0:
                self.outputArea.append("Decomposição concluída com sucesso.")
            else:
                self.outputArea.append(f"Erro na decomposição: código {code}")

        self.currentProcess.finished.connect(finished)
        self.connectProcessSignals(self.currentProcess)
        self.currentProcess.start("bash", ["-l", "-c", command])
    
    def clearSimulation(self):
        caseDir = QDir("/home/gaf/build-GAFoam-Desktop-Debug")
        timeDirs = caseDir.entryList(QDir.Dirs | QDir.NoDotAndDotDot)
        removedAny = False
        
        for dirName in timeDirs:
            try:
                timeValue = float(dirName)
                if timeValue > 0:
                    timeDir = QDir(caseDir.filePath(dirName))
                    if timeDir.removeRecursively():
                        self.outputArea.append(f"Removendo pasta de tempo: {dirName}")
                        removedAny = True
            except ValueError:
                pass
        
        if removedAny:
            self.outputArea.append("Pastas de tempo reconstruídas removidas.")
        else:
            self.outputArea.append("Nenhuma pasta de tempo encontrada.")

    def runSimulation(self):
        start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.outputArea.append("Iniciando simulação...")
        
        if not self.unvFilePath:
            self.outputArea.append("Erro: Nenhum caso ou arquivo .unv selecionado.")
            return

        # Verifica se é uma pasta de caso válida
        if QDir(self.unvFilePath).exists("0") and QDir(self.unvFilePath).exists("system") and QDir(self.unvFilePath).exists("constant"):
            casePath = self.unvFilePath
        elif self.unvFilePath.endswith(".unv"):
            casePath = QFileInfo(self.unvFilePath).absolutePath()
        else:
            self.outputArea.append("Erro: O caminho selecionado não é válido.")
            return

        if not self.currentSolver:
            self.outputArea.append("Erro: Nenhum solver selecionado.")
            return

        self.clearResidualPlot()

        if self.currentOpenFOAMVersion == "openfoam12":
            command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && mpirun -np 2 foamRun -parallel"'
        else:
            command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && mpirun -np 2 {self.currentSolver} -parallel"'

        self.outputArea.append(f"Iniciando simulação com {self.currentSolver}...")
        self.currentProcess = QProcess(self)
        self.setupProcessEnvironment(self.currentProcess)

        # Define a pasta do caso como diretório de trabalho
        self.currentProcess.setWorkingDirectory(casePath)

        def finished(code):
            if code == 0:
                self.outputArea.append("Simulação concluída com sucesso.")
            else:
                self.outputArea.append(f"Erro na simulação: código {code}")

        self.currentProcess.finished.connect(finished)
        self.connectProcessSignals(self.currentProcess)
        self.outputArea.append(f"Comando executado: {command}")

        self.currentProcess.start("bash", ["-l", "-c", command])
        self.currentProcess.finished.connect(lambda: self.logSimulationCompletion(start_time))
    
    def clearDecomposedProcessors(self):
        if not self.unvFilePath:
            self.outputArea.append("Erro: Nenhum caso selecionado.")
            return

        caseDir = QDir(self.unvFilePath)
        processorDirs = caseDir.entryList(["processor*"], QDir.Dirs | QDir.NoDotAndDotDot)
        removedAny = False

        for dirName in processorDirs:
            processorDir = QDir(caseDir.filePath(dirName))
            if processorDir.removeRecursively():
                self.outputArea.append(f"Removendo pasta: {dirName}")
                removedAny = True

        if removedAny:
            self.outputArea.append("Pastas de decomposição removidas com sucesso.")
        else:
            self.outputArea.append("Nenhuma pasta de decomposição encontrada.")
    
    def stopSimulation(self):
        """Para o processo de simulação em execução"""
        if self.currentProcess and self.currentProcess.state() == QProcess.Running:
            self.currentProcess.terminate() 
            if not self.currentProcess.waitForFinished(3000):  
                self.currentProcess.kill()  
            self.outputArea.append("Simulação interrompida.")
            self.currentProcess = None
        else:
            self.outputArea.append("Nenhuma simulação em execução para parar.")
    
    def clearTerminal(self):
        self.outputArea.clear()
        self.outputArea.append("Terminal limpo.", 2000)
    
    def editFile(self):
        """Abre um arquivo para edição no editor."""
        fileName, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher Arquivo de Código",
            self.systemDir,
            "Todos os Arquivos (*);;Arquivos de Código (*.dict *.txt *.swp)"
        )
        if fileName:
            file = QtCore.QFile(fileName)
            if file.open(QtCore.QIODevice.ReadOnly | QtCore.QIODevice.Text):
                self.currentFilePath = fileName
                self.fileEditor.setPlainText(str(file.readAll(), 'utf-8'))
                file.close()
                self.outputArea.append(f"Arquivo de código aberto: {fileName}")
            else:
                self.outputArea.append("Erro ao abrir o arquivo para edição.")
        else:
            self.outputArea.append("Nenhum arquivo selecionado.")
    
    def saveFile(self):
        if not self.currentFilePath:
            self.outputArea.append("Nenhum arquivo carregado para salvar.")
            return
        
        file = QtCore.QFile(self.currentFilePath)
        if file.open(QtCore.QIODevice.WriteOnly | QtCore.QIODevice.Text):
            file.write(self.fileEditor.toPlainText().encode('utf-8'))
            file.close()
            self.outputArea.append(f"Arquivo salvo com sucesso: {self.currentFilePath}")
        else:
            self.outputArea.append("Erro ao salvar o arquivo.")
    
    def executeTerminalCommand(self):
        command = self.terminalInput.text()
        if command:
            self.outputArea.append(f"> {command}")
            self.terminalInput.clear()
            
            process = QProcess(self)
            self.setupProcessEnvironment(process)
            self.connectProcessSignals(process)
            
            fullCommand = f'source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && {command}'
            process.start("bash", ["-l", "-c", fullCommand])
            
            firstWord = command.split(' ')[0]
            self.outputArea.append(f"Comando executado: {firstWord}", 2000)
    
    def setupProcessEnvironment(self, process):
        env = QProcessEnvironment.systemEnvironment()
        env.insert("FOAM_RUN", f"/opt/{self.currentOpenFOAMVersion}")
        process.setProcessEnvironment(env)
    
    def connectProcessSignals(self, process):
        """Conecta os sinais do processo para capturar saída e atualizar resíduos."""
        def readOutput():
            while process.canReadLine():
                output = str(process.readLine(), 'utf-8').strip()
                self.outputArea.append(output)
                self.parseResiduals(output)
                QApplication.processEvents() 

        def readError():
            while process.canReadLine():
                error = str(process.readLineStandardError(), 'utf-8').strip()
                self.outputArea.append(error)

        process.readyReadStandardOutput.connect(readOutput)
        process.readyReadStandardError.connect(readError)


    def calculateRates(self):
        try:
            # Parâmetros de exemplo
            d = 0.106
            n = 30
            m = 10
            dy_in_0 = 0.00142
            dy_wall_0 = 0.008

            results = calculate_increase_rate(d, n, m, dy_in_0, dy_wall_0)

            # Exibir os resultados na área de saída
            self.outputArea.append("Resultados do cálculo de Δy")
            for key, value in results.items():
                self.outputArea.append(f"{key}: {value:.5f}" if isinstance(value, float) else f"{key}: {value}")
        except Exception as e:
            self.outputArea.append(f"Erro ao calcular taxas: {str(e)}")

    def openRateCalculationDialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Calcular Δy")
        dialog.setModal(True)
        dialog.resize(300, 200)

        layout = QVBoxLayout(dialog)

        # Campos de entrada
        dLabel = QLabel("d (diâmetro):", dialog)
        dInput = QLineEdit(dialog)
        dInput.setPlaceholderText("Exemplo: 0.106")

        nLabel = QLabel("n (distância do bocal):", dialog)
        nInput = QLineEdit(dialog)
        nInput.setPlaceholderText("Exemplo: 30")

        mLabel = QLabel("m (distância de transição):", dialog)
        mInput = QLineEdit(dialog)
        mInput.setPlaceholderText("Exemplo: 10")

        dyIn0Label = QLabel("dy_in_0 (altura inicial):", dialog)
        dyIn0Input = QLineEdit(dialog)
        dyIn0Input.setPlaceholderText("Exemplo: 0.00142")

        dyWall0Label = QLabel("dy_wall_0 (altura na parede):", dialog)
        dyWall0Input = QLineEdit(dialog)
        dyWall0Input.setPlaceholderText("Exemplo: 0.008")

        # Botão para calcular
        calculateButton = QPushButton("Calcular", dialog)
        calculateButton.clicked.connect(lambda: self.calculateRatesFromDialog(
            dialog, dInput.text(), nInput.text(), mInput.text(), dyIn0Input.text(), dyWall0Input.text()
        ))

        # Adicionar widgets ao layout
        layout.addWidget(dLabel)
        layout.addWidget(dInput)
        layout.addWidget(nLabel)
        layout.addWidget(nInput)
        layout.addWidget(mLabel)
        layout.addWidget(mInput)
        layout.addWidget(dyIn0Label)
        layout.addWidget(dyIn0Input)
        layout.addWidget(dyWall0Label)
        layout.addWidget(dyWall0Input)
        layout.addWidget(calculateButton)

        dialog.exec_()

    def calculateRatesFromDialog(self, dialog, d, n, m, dy_in_0, dy_wall_0):
        try:
            
            d = float(d)
            n = float(n)
            m = float(m)
            dy_in_0 = float(dy_in_0)
            dy_wall_0 = float(dy_wall_0)

            results = calculate_increase_rate(d, n, m, dy_in_0, dy_wall_0)

            self.outputArea.append("Resultados do cálculo de Δy")
            for key, value in results.items():
                self.outputArea.append(f"{key}: {value:.5f}" if isinstance(value, float) else f"{key}: {value}")

            dialog.accept()
        except ValueError:
            self.outputArea.append("Erro: Certifique-se de que todos os valores são números válidos.")
        except Exception as e:
            self.outputArea.append(f"Erro ao calcular taxas: {str(e)}")

    def openFluidPropertiesDialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Calcular Propriedades do Fluido")
        dialog.setModal(True)
        dialog.resize(300, 300)

        layout = QVBoxLayout(dialog)

        # Campos de entrada
        tempLabel = QLabel("Temperatura (°C):", dialog)
        tempInput = QLineEdit(dialog)
        tempInput.setPlaceholderText("Exemplo: 46.6")

        pressureLabel = QLabel("Pressão (MPa):", dialog)
        pressureInput = QLineEdit(dialog)
        pressureInput.setPlaceholderText("Exemplo: 9.64")

        salinityLabel = QLabel("Salinidade (mg/L):", dialog)
        salinityInput = QLineEdit(dialog)
        salinityInput.setPlaceholderText("Exemplo: 323000")

        # Botão para calcular
        calculateButton = QPushButton("Calcular", dialog)
        calculateButton.clicked.connect(lambda: self.calculateFluidProperties(
            dialog, tempInput.text(), pressureInput.text(), salinityInput.text()
        ))

        # Adicionar widgets ao layout
        layout.addWidget(tempLabel)
        layout.addWidget(tempInput)
        layout.addWidget(pressureLabel)
        layout.addWidget(pressureInput)
        layout.addWidget(salinityLabel)
        layout.addWidget(salinityInput)
        layout.addWidget(calculateButton)

        dialog.exec_()

    def calculateFluidProperties(self, dialog, temp, pressure, salinity):
        try:
            temp = float(temp)
            pressure = float(pressure) * 10  # Converte MPa para bar
            salinity = float(salinity) / 1e6  # Converte mg/L para fração mássica

            fluid = FluidProperties()

            density = fluid.brine_density(temp, pressure, salinity)
            viscosity = fluid.brine_viscosity(temp, pressure, salinity) * 1000  # Converte Pa.s para mPa.s

            self.outputArea.append("Resultados das Propriedades do Fluido:")
            self.outputArea.append(f"Temperatura: {temp} °C")
            self.outputArea.append(f"Pressão: {pressure} bar")
            self.outputArea.append(f"Salinidade: {salinity:.6f} (fração mássica)")
            self.outputArea.append(f"Densidade: {density:.2f} kg/m³")
            self.outputArea.append(f"Viscosidade: {viscosity:.6f} mPa·s")

            dialog.accept()
        except ValueError:
            self.outputArea.append("Erro: Certifique-se de que todos os valores são números válidos.")
        except Exception as e:
            self.outputArea.append(f"Erro ao calcular propriedades: {str(e)}")

    def openSimulationHistory(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Histórico de Simulações")
        dialog.resize(800, 400)

        layout = QVBoxLayout(dialog)

        self.historyTable = QTableWidget(dialog)
        self.historyTable.setColumnCount(5)
        self.historyTable.setHorizontalHeaderLabels(["Solver", "Malha", "Início", "Fim", "Status"])
        self.loadHistoryIntoTable()
        layout.addWidget(self.historyTable)

        buttonLayout = QHBoxLayout()
        
        clearAllButton = QPushButton("Limpar Tudo", dialog)
        clearAllButton.clicked.connect(self.clearAllSimulations)
        buttonLayout.addWidget(clearAllButton)

        deleteSelectedButton = QPushButton("Excluir Selecionado", dialog)
        deleteSelectedButton.clicked.connect(self.deleteSelectedSimulation)
        buttonLayout.addWidget(deleteSelectedButton)

        layout.addLayout(buttonLayout)
        dialog.setLayout(layout)
        dialog.exec_()

    def loadHistoryIntoTable(self):
        """Carrega o histórico na tabela."""
        history = self.simulationHistory.get_history()
        self.historyTable.setRowCount(len(history))
        for row, entry in enumerate(history):
            self.historyTable.setItem(row, 0, QTableWidgetItem(entry["solver"]))
            self.historyTable.setItem(row, 1, QTableWidgetItem(entry["case_path"]))
            self.historyTable.setItem(row, 2, QTableWidgetItem(entry["start_time"]))
            self.historyTable.setItem(row, 3, QTableWidgetItem(entry["end_time"]))
            self.historyTable.setItem(row, 4, QTableWidgetItem(entry["status"]))

    def clearAllSimulations(self):
        """Limpa todo o histórico de simulações."""
        reply = QMessageBox.question(
            self, "Confirmação", "Tem certeza de que deseja limpar todo o histórico?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.simulationHistory.history = []  # Limpa o histórico na memória
            self.simulationHistory.save_history()  # Salva o histórico vazio no arquivo
            self.loadHistoryIntoTable()  # Atualiza a tabela
            QMessageBox.information(self, "Histórico Limpo", "Todo o histórico foi limpo com sucesso.")

    def deleteSelectedSimulation(self):
        """Exclui a simulação selecionada na tabela."""
        selectedRow = self.historyTable.currentRow()
        if selectedRow == -1:
            QMessageBox.warning(self, "Nenhuma Seleção", "Por favor, selecione uma simulação para excluir.")
            return

        reply = QMessageBox.question(
            self, "Confirmação", "Tem certeza de que deseja excluir a simulação selecionada?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            del self.simulationHistory.history[selectedRow]  # Remove a entrada do histórico
            self.simulationHistory.save_history()  # Salva as alterações no arquivo
            self.loadHistoryIntoTable()  # Atualiza a tabela
            QMessageBox.information(self, "Simulação Excluída", "A simulação selecionada foi excluída com sucesso.")

    def filterTreeView(self, text):
        """Filtra os itens da árvore de diretórios com base no texto inserido."""
        def filterItems(item, text):
            match = text.lower() in item.text().lower()
            for row in range(item.rowCount()):
                child = item.child(row)
                match = filterItems(child, text) or match
            item.setHidden(match)
            return match

        for row in range(self.treeModel.rowCount()):
            rootItem = self.treeModel.item(row)
            filterItems(rootItem, text)

    def configureDecomposeParCores(self):
        """Abre um diálogo para configurar o número de núcleos e atualiza o decomposeParDict."""
        num_cores, ok = QInputDialog.getInt(
            self,
            "Configurar Núcleos",
            "Digite o número de núcleos para decomposePar:",
            min=1,
            max=128,  # Limite máximo de núcleos
            value=2   # Valor padrão
        )
        if ok:
            self.num_cores = num_cores  # Armazena o número de núcleos como atributo da classe
            decompose_par_dict_path = "/home/gaf/build-GAFoam-Desktop-Debug/system/decomposeParDict"
            try:
                # Ler o arquivo decomposeParDict
                with open(decompose_par_dict_path, "r") as file:
                    lines = file.readlines()

                # Atualizar o valor de numberOfSubdomains
                with open(decompose_par_dict_path, "w") as file:
                    for line in lines:
                        if "numberOfSubdomains" in line:
                            file.write(f"numberOfSubdomains {num_cores};\n")
                        else:
                            file.write(line)

                self.outputArea.append(f"Arquivo decomposeParDict atualizado com {num_cores} núcleos.")
            except FileNotFoundError:
                self.outputArea.append("Erro: Arquivo decomposeParDict não encontrado.")
            except Exception as e:
                self.outputArea.append(f"Erro ao atualizar decomposeParDict: {str(e)}")

    def load_config(self):
        """Carrega as configurações do arquivo config.json."""
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as file:
                return json.load(file)
        else:
            return {}

    def save_config(self):
        """Salva as configurações no arquivo config.json."""
        with open(self.config_file, "w") as file:
            json.dump(self.config, file, indent=4)

    def set_base_dir(self):
        """Permite ao usuário definir o diretório base."""
        baseDir = QFileDialog.getExistingDirectory(
            self, "Escolher Diretório Base", os.getcwd(), QFileDialog.ShowDirsOnly
        )
        if baseDir:
            self.baseDir = baseDir
            self.systemDir = os.path.join(self.baseDir, "system")
            self.config["baseDir"] = self.baseDir
            self.save_config()
            self.outputArea.append(f"Diretório base configurado para: {self.baseDir}")
        else:
            self.outputArea.append("Nenhum diretório base selecionado.")

class FluidProperties:
    def __init__(self):
        # Constantes para densidade da água (Palliser & McKibbin modelo I)
        self.c0, self.c1, self.c2, self.c3 = 999.84, 0.0679, -0.0085, 0.0001
        self.A, self.B = 0.51, -0.0002  # Coeficientes de pressão em bar
        self.mu_c_800 = 2.0  # Viscosidade do NaCl fundido a 800°C em cP (exemplo)
        self.mu_w_base = 0.00089  # Viscosidade da água em condições padrão em Pa.s

    def water_density(self, T, P):
        """Calcula a densidade da água pura (rho_w) em função da temperatura (T) e pressão (P)."""
        rho_0 = self.c0 + self.c1 * T + self.c2 * T**2 + self.c3 * T**3
        rho_w = rho_0 + self.A * P + self.B * P**2
        return rho_w

    def brine_density(self, T, P, X):
        """Calcula a densidade da salmoura (rho_b) em função de T, P e salinidade (X)."""
        rho_w_TP = self.water_density(T, P)
        rho_b = rho_w_TP + X * (1695 - rho_w_TP)
        return rho_b

    def brine_viscosity(self, T, P, X):
        """Calcula a viscosidade da salmoura (mu_b) em função de T, P e salinidade (X)."""
        if T < 800:
            term1 = self.mu_w_base * (1 + 3 * X) * ((800 - T) / 800) ** 9
            term2 = ((T / 800) ** 9) * (self.mu_w_base * (1 - X) + X * self.mu_c_800)
            mu_b = (term1 + term2) / (((800 - T) / 800) ** 9 + (T / 800) ** 9)
        else:
            mu_b = self.mu_w_base * (1 - X) + self.mu_c_800 * X
        return mu_b

# Atualize o método calculateFluidProperties para incluir o cálculo da viscosidade
def calculateFluidProperties(self, dialog, temp, pressure, salinity):
    try:
        temp = float(temp)
        pressure = float(pressure) * 10  # Converte MPa para bar
        salinity = float(salinity) / 1e6  # Converte mg/L para fração mássica

        fluid = FluidProperties()

        density = fluid.brine_density(temp, pressure, salinity)
        viscosity = fluid.brine_viscosity(temp, pressure, salinity) * 1000  # Converte Pa.s para mPa.s

        self.outputArea.append("Resultados das Propriedades do Fluido:")
        self.outputArea.append(f"Temperatura: {temp} °C")
        self.outputArea.append(f"Pressão: {pressure} bar")
        self.outputArea.append(f"Salinidade: {salinity:.6f} (fração mássica)")
        self.outputArea.append(f"Densidade: {density:.2f} kg/m³")
        self.outputArea.append(f"Viscosidade: {viscosity:.6f} mPa·s")

        dialog.accept()
    except ValueError:
        self.outputArea.append("Erro: Certifique-se de que todos os valores são números válidos.")
    except Exception as e:
        self.outputArea.append(f"Erro ao calcular propriedades: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    interface = OpenFOAMInterface()
    interface.show()
    
    sys.exit(app.exec_())
