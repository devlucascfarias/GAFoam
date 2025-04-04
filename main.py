import os
import sys
import re
import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import (QApplication, QWidget, QWidgetAction, QPushButton, QVBoxLayout, QHBoxLayout, 
                             QFileDialog, QTextEdit, QLabel, QMenuBar, QMenu, QAction, 
                             QLineEdit, QStatusBar, QTreeView, QComboBox)
from PyQt5.QtCore import QTimer, QProcess, Qt, QDir, QFileInfo, QProcessEnvironment
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QIcon
from PyQt5 import QtCore

class OpenFOAMInterface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GAFoam")
        self.resize(1000, 600)
        
        self.unvFilePath = ""
        self.currentFilePath = ""
        self.currentOpenFOAMVersion = "openfoam9"
        self.currentSolver = "twoLiquidMixingFoam"
        self.currentProcess = None
        
        # Dados para gráfico de resíduos
        self.residualData = {}
        self.timeData = []
        self.residualLines = {}
        self.colors = ['r', 'g', 'b', 'c', 'm', 'y', 'w']  # Cores para diferentes variáveis
        
        self.mainVerticalLayout = QVBoxLayout(self)
        self.mainVerticalLayout.setContentsMargins(5, 5, 5, 5)
        
        self.setupMenuBar()
        self.setupMainContentArea()
        self.setupStatusBar()
        
        self.systemMonitorTimer = QTimer(self)
        self.systemMonitorTimer.timeout.connect(self.updateSystemUsage)
        self.systemMonitorTimer.start(2000)
        
        self.setLayout(self.mainVerticalLayout)
    
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
    
    def setupMenuBar(self):
        self.menuBar = QMenuBar(self)
        
        fileMenu = QMenu("Arquivo", self.menuBar)
        
        refreshTreeAction = QAction("Atualizar Árvore", self)
        refreshTreeAction.triggered.connect(lambda: self.populateTreeView(QFileInfo(self.unvFilePath).absolutePath() if self.unvFilePath else None))
        
        checkMeshAction = QAction("Checar Malha", self)
        checkMeshAction.triggered.connect(self.checkMesh)
        
        importUNVAction = QAction("Importar Arquivo (.unv)", self)
        importUNVAction.triggered.connect(self.chooseUNV)
        
        fileMenu.addAction(refreshTreeAction)
        fileMenu.addAction(checkMeshAction)
        fileMenu.addAction(importUNVAction)
        
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
        
        self.mainVerticalLayout.setMenuBar(self.menuBar)
    
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
            solverDir = QDir(solverPath)
            self.currentSolver = solverDir.dirName()
            self.outputArea.append(f"Solver selecionado: {self.currentSolver}")
            self.outputArea.append(f"Solver definido: {self.currentSolver}")
    
    def setupMainContentArea(self):
        contentLayout = QHBoxLayout()
        
        # Área do terminal (esquerda)
        leftContentLayout = QVBoxLayout()
        terminalLayout = QVBoxLayout()
        terminalLayout.addWidget(QLabel("Terminal e Logs", self))
        
        self.openParaviewButton = QPushButton("Abrir no ParaView", self)
        self.openParaviewButton.clicked.connect(self.openParaview)
        terminalLayout.addWidget(self.openParaviewButton)
        
        self.outputArea = QTextEdit(self)
        self.outputArea.setReadOnly(True)
        terminalLayout.addWidget(self.outputArea)
        
        self.terminalInput = QLineEdit(self)
        self.terminalInput.setPlaceholderText(">>")
        self.terminalInput.returnPressed.connect(self.executeTerminalCommand)
        terminalLayout.addWidget(self.terminalInput)
        
        leftContentLayout.addLayout(terminalLayout)
        
        # Adicionar gráfico de resíduos
        residualLayout = QVBoxLayout()
        residualLayout.addWidget(QLabel("Gráfico de Resíduos", self))
        
        self.graphWidget = pg.PlotWidget()
        self.graphWidget.setLabel('left', 'Resíduos')
        self.graphWidget.setLabel('bottom', 'Tempo')
        self.graphWidget.setLogMode(y=True)  
        self.graphWidget.showGrid(x=True, y=True)
        self.graphWidget.addLegend()
        residualLayout.addWidget(self.graphWidget)
        
        graphControlLayout = QHBoxLayout()

        self.clearPlotButton = QPushButton("Limpar Gráfico", self)
        self.clearPlotButton.clicked.connect(self.clearResidualPlot)

        self.toggleLogScaleButton = QPushButton("Alternar Escala Log", self)
        self.toggleLogScaleButton.clicked.connect(self.toggleLogScale)  

        self.exportPlotDataButton = QPushButton("Exportar Dados", self)
        self.exportPlotDataButton.clicked.connect(self.exportPlotData)  

        graphControlLayout.addWidget(self.clearPlotButton)
        graphControlLayout.addWidget(self.toggleLogScaleButton)
        graphControlLayout.addWidget(self.exportPlotDataButton)

        self.mockDataButton = QPushButton("Gerar Dados Fictícios", self)
        self.mockDataButton.clicked.connect(self.generateMockData)
        graphControlLayout.addWidget(self.mockDataButton)

        residualLayout.addLayout(graphControlLayout)
        
        leftContentLayout.addLayout(residualLayout)
        
        # Botões

        buttonLayout = QVBoxLayout()
        
        self.convertButton = QPushButton("Converter Malha", self)
        self.convertButton.clicked.connect(self.convertMesh)
        
        self.decomposeParButton = QPushButton("Decompor Núcleos", self)
        self.decomposeParButton.clicked.connect(self.decomposePar)
        
        self.runButton = QPushButton("Rodar Simulação", self)
        self.runButton.clicked.connect(self.runSimulation)
        
        self.stopButton = QPushButton("Parar Simulação", self)
        self.stopButton.clicked.connect(self.stopSimulation)
        
        self.reconstructButton = QPushButton("Reconstruir", self)
        self.reconstructButton.clicked.connect(self.reconstructPar)
        
        self.clearDecomposeButton = QPushButton("Limpar Processadores", self)
        self.clearDecomposeButton.clicked.connect(self.clearDecomposedProcessors)
        
        self.clearSimulationButton = QPushButton("Limpar Arquivos de Simulação", self)
        self.clearSimulationButton.clicked.connect(self.clearSimulation)
        
        # Adiciona botões ao layout
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
        editorLayout.addWidget(self.fileEditor)
        
        self.editButton = QPushButton("Editar Arquivo", self)
        self.editButton.clicked.connect(self.editFile)
        
        self.saveButton = QPushButton("Salvar Arquivo", self)
        self.saveButton.clicked.connect(self.saveFile)
        
        editorLayout.addWidget(self.editButton)
        editorLayout.addWidget(self.saveButton)
        
        # Árvore de diretórios (direita)
        treeLayout = QVBoxLayout()
        treeLayout.addWidget(QLabel("Diretórios", self))
        
        self.treeView = QTreeView(self)
        self.treeModel = QStandardItemModel(self)
        self.treeView.setModel(self.treeModel)
        self.treeView.setHeaderHidden(True)
        self.treeView.doubleClicked.connect(self.onTreeViewDoubleClicked)
        
        treeLayout.addWidget(self.treeView)
        
        # Adiciona os layouts ao layout principal
        contentLayout.addLayout(leftContentLayout, 3)
        contentLayout.addLayout(editorLayout, 1)
        contentLayout.addLayout(treeLayout, 1)
        
        self.mainVerticalLayout.addLayout(contentLayout, 1)

        self.treeUpdateTimer = QTimer(self)
        self.treeUpdateTimer.timeout.connect(lambda: self.populateTreeView())
        self.treeUpdateTimer.start(5000)  # Atualiza a cada 5 segundos

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
        self.cpuUsageLabel = QLabel("CPU: --%", self.statusBar)
        self.memUsageLabel = QLabel("Memória: --%", self.statusBar)
        
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
    
    def chooseUNV(self):
        fileName, _ = QFileDialog.getOpenFileName(
            self, 
            "Escolher Arquivo UNV", 
            "", 
            "Arquivos UNV (*.unv)"
        )
        
        if fileName:
            self.unvFilePath = fileName
            self.outputArea.append(f"Arquivo UNV escolhido: {fileName}")
            self.meshPathLabel.setText(f"Malha: {QFileInfo(fileName).fileName()}")
            self.outputArea.append("Malha carregada.")
            self.populateTreeView(QFileInfo(fileName).absolutePath())
    
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
    
    def parseResiduals(self, text):
        """Analisa o texto de saída para extrair dados de resíduos"""
        lines = text.strip().split('\n')
        current_time = None
        
        for line in lines:
            # Captura o tempo atual
            time_match = re.search(r'Time\s*=\s*([0-9.e+-]+)', line)
            if time_match:
                current_time = float(time_match.group(1))
                if current_time not in self.timeData:
                    self.timeData.append(current_time)
                    self.outputArea.append(f"Tempo detectado: {current_time}")
                continue
            
            # Captura resíduos iniciais no formato do OpenFOAM
            # Exemplo: "smoothSolver:  Solving for Ux, Initial residual = 1, Final residual = 4.60944e-08, No Iterations 6"
            # Ou: "GAMG:  Solving for p_rgh, Initial residual = 1, Final residual = 0.0094947, No Iterations 59"
            residual_match = re.search(r'(?:smoothSolver|GAMG|PCG|PBiCGStab):\s+Solving for ([a-zA-Z0-9_]+), Initial residual = ([0-9.e+-]+)', line)
            if residual_match and current_time is not None:
                variable = residual_match.group(1)
                residual = float(residual_match.group(2))
                
                if variable not in self.residualData:
                    self.residualData[variable] = []
                    color_idx = len(self.residualData) % len(self.colors)
                    pen = pg.mkPen(color=self.colors[color_idx], width=2)
                    self.residualLines[variable] = self.graphWidget.plot(
                        [], [], name=variable, pen=pen, symbolBrush=self.colors[color_idx], 
                        symbolPen='w', symbol='o', symbolSize=5
                    )
                    self.outputArea.append(f"Nova variável detectada: {variable}")
                    
                # Certifica-se de que os dados têm o mesmo comprimento
                while len(self.residualData[variable]) < len(self.timeData) - 1:
                    self.residualData[variable].append(None)
                
                self.residualData[variable].append(residual)
                
                # Atualiza o gráfico
                self.updateResidualPlot(variable)
    
    def updateResidualPlot(self, variable):
        """Atualiza o gráfico de resíduos para a variável especificada"""
        if variable in self.residualLines and variable in self.residualData:
            valid_data = [(time, res) for time, res in zip(self.timeData, self.residualData[variable]) 
                         if res is not None]
            if valid_data:
                x_data, y_data = zip(*valid_data)
                self.residualLines[variable].setData(x_data, y_data)

    def clearResidualPlot(self):
        """Limpa o gráfico de resíduos"""
        self.timeData = []
        self.residualData = {}
        self.graphWidget.clear()
        self.residualLines = {}

    def connectProcessSignals(self, process):
        """Conecta os sinais do processo para capturar saída e erros"""
        def readOutput():
            while process.canReadLine():
                output = str(process.readLine(), 'utf-8').strip()
                self.outputArea.append(output)
                self.parseResiduals(output)  # Analisa resíduos em tempo real
        
        def readError():
            while process.canReadLine():
                error = str(process.readLineStandardError(), 'utf-8').strip()
                self.outputArea.append(error)
        
        def handleError(error):
            self.outputArea.append(f"Erro no processo: {error}", 5000)
        
        process.readyReadStandardOutput.connect(readOutput)
        process.readyReadStandardError.connect(readError)
        process.errorOccurred.connect(handleError)

    def runSimulation(self):
        if not self.unvFilePath:
            self.outputArea.append("Erro: Nenhum arquivo UNV selecionado")
            return
        
        if not self.currentSolver:
            self.outputArea.append("Erro: Nenhum solver selecionado")
            return
        
        # Limpa o gráfico de resíduos antes de começar nova simulação
        self.clearResidualPlot()
        
        self.outputArea.append(f"Iniciando simulação com {self.currentSolver}...")
        command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && mpirun -np 6 {self.currentSolver} -parallel"'
        
        self.currentProcess = QProcess(self)
        self.setupProcessEnvironment(self.currentProcess)
        
        def finished(code):
            self.outputArea.append(f"Simulação finalizada com código {code}", 5000)
            self.currentProcess = None
        
        self.currentProcess.finished.connect(finished)
        self.connectProcessSignals(self.currentProcess)
        self.outputArea.append(f"Comando executado: {command}")
        
        # Inicia o processo sem bloqueio
        self.currentProcess.start("bash", ["-l", "-c", command])

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
            self.outputArea.append("Erro: Nenhum arquivo UNV selecionado")
            return
        
        self.outputArea.append("Executando decomposePar...")
        command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && decomposePar"'
        
        process = QProcess(self)
        self.setupProcessEnvironment(process)
        self.connectProcessSignals(process)
        self.outputArea.append(f"Comando executado: {command}")
        process.start(command)
    
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
    
    def clearDecomposedProcessors(self):
        caseDir = QDir("/home/gaf/build-GAFoam-Desktop-Debug")
        processorDirs = caseDir.entryList(["processor*"], QDir.Dirs | QDir.NoDotAndDotDot)
        removedAny = False
        
        for dirName in processorDirs:
            processorDir = QDir(caseDir.filePath(dirName))
            if processorDir.removeRecursively():
                self.outputArea.append(f"Removendo pasta: {dirName}")
                removedAny = True
        
        if removedAny:
            self.outputArea.append("Pastas de decomposição removidas.")
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
        systemDir = "/home/gaf/build-GAFoam-Desktop-Debug/system"
        print(f"Diretório escolhido: {systemDir}")
        
        fileName, _ = QFileDialog.getOpenFileName(
            self,
            "Escolher Arquivo de Código",
            systemDir,
            "Todos os Arquivos (*);;Arquivos de Código (*.dict *.txt *.swp)"
        )
        
        if fileName:
            print(f"Arquivo selecionado: {fileName}")
            
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
        """Conecta os sinais do processo para capturar saída e erros"""
        def readOutput():
            while process.canReadLine():
                output = str(process.readLine(), 'utf-8').strip()
                self.outputArea.append(output)
                self.parseResiduals(output)  # Analisa resíduos em tempo real
        
        def readError():
            while process.canReadLine():
                error = str(process.readLineStandardError(), 'utf-8').strip()
                self.outputArea.append(error)
        
        def handleError(error):
            self.outputArea.append(f"Erro no processo: {error}", 5000)
        
        process.readyReadStandardOutput.connect(readOutput)
        process.readyReadStandardError.connect(readError)
        process.errorOccurred.connect(handleError)

    def generateMockData(self):
        """Gera dados fictícios para testar o gráfico de resíduos"""
        import numpy as np

        # Limpa os dados existentes
        self.clearResidualPlot()

        # Gera dados fictícios
        self.timeData = np.linspace(0, 300, 100)  # 100 pontos de tempo entre 0 e 300
        variables = ['epsilon', 'k', 'Ux', 'Uy']
        for i, variable in enumerate(variables):
            residuals = np.exp(-0.01 * self.timeData) * (1 + 0.1 * np.random.randn(len(self.timeData)))
            self.residualData[variable] = residuals

            # Adiciona a curva ao gráfico
            color_idx = i % len(self.colors)
            pen = pg.mkPen(color=self.colors[color_idx], width=2)
            self.residualLines[variable] = self.graphWidget.plot(
                self.timeData, residuals, name=variable, pen=pen, symbolBrush=self.colors[color_idx],
                symbolPen='w', symbol='o', symbolSize=5
            )

        self.outputArea.append("Dados fictícios gerados para teste do gráfico")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    interface = OpenFOAMInterface()
    interface.show()
    
    sys.exit(app.exec_())
