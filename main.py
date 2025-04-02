import os
import sys
import re
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
        self.statusBar.showMessage(f"Versão selecionada: {version}", 3000)
    
    def selectSolver(self):
        solverPath = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Pasta do Solver",
            f"/opt/{self.currentOpenFOAMVersion}/applications/solvers"
        )
        
        if solverPath:
            solverDir = QDir(solverPath)
            self.currentSolver = solverDir.dirName()
            self.statusBar.showMessage(f"Solver selecionado: {self.currentSolver}", 3000)
            self.outputArea.append(f"Solver definido: {self.currentSolver}")
    
    def setupMainContentArea(self):
        contentLayout = QHBoxLayout()
        
        # Área do terminal (esquerda)
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
        
        # Botões de ação
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
        terminalLayout.addWidget(self.convertButton)
        terminalLayout.addWidget(self.decomposeParButton)
        terminalLayout.addWidget(self.runButton)
        terminalLayout.addWidget(self.stopButton)
        terminalLayout.addWidget(self.reconstructButton)
        terminalLayout.addWidget(self.clearDecomposeButton)
        terminalLayout.addWidget(self.clearSimulationButton)
        
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
        contentLayout.addLayout(terminalLayout, 1)
        contentLayout.addLayout(editorLayout, 1)
        contentLayout.addLayout(treeLayout, 1)
        
        self.mainVerticalLayout.addLayout(contentLayout, 1)
    
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
                    self.statusBar.showMessage(f"Arquivo carregado: {filePath}", 3000)
    
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
    
    def populateTreeView(self, casePath):
        self.treeModel.clear()
        self.treeModel.setHorizontalHeaderLabels(["Estrutura do Caso"])
        
        caseDir = QDir(casePath)
        if not caseDir.exists():
            self.outputArea.append(f"Diretório do caso não encontrado: {casePath}")
            return
        
        rootItem = self.treeModel.invisibleRootItem()
        self.addDirectoryToTree(caseDir.path(), rootItem)
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
            self.statusBar.showMessage("Erro: Nenhum caso selecionado", 3000)
            return
        
        caseDir = QFileInfo(self.unvFilePath).absolutePath()
        command = f"paraview --data={caseDir}/foam.foam"
        
        process = QProcess(self)
        process.start(command)
        
        if not process.waitForStarted():
            self.statusBar.showMessage("Erro ao abrir o ParaView", 3000)
        else:
            self.statusBar.showMessage("ParaView iniciado com sucesso", 3000)
    
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
            self.statusBar.showMessage("Malha carregada com sucesso", 3000)
            self.populateTreeView(QFileInfo(fileName).absolutePath())
    
    def checkMesh(self):
        if not self.unvFilePath:
            self.statusBar.showMessage("Erro: Nenhum arquivo UNV selecionado", 3000)
            return
        
        self.statusBar.showMessage("Executando checkMesh...")
        command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && checkMesh"'
        
        process = QProcess(self)
        self.setupProcessEnvironment(process)
        self.connectProcessSignals(process)
        self.outputArea.append(f"Comando executado: {command}")
        process.start(command)
    
    def convertMesh(self):
        if not self.unvFilePath:
            self.statusBar.showMessage("Erro: Nenhum arquivo UNV selecionado", 3000)
            return
        
        self.statusBar.showMessage("Convertendo malha para OpenFOAM...")
        command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && ideasUnvToFoam {self.unvFilePath}"'
        
        process = QProcess(self)
        self.setupProcessEnvironment(process)
        self.connectProcessSignals(process)
        self.outputArea.append(f"Comando executado: {command}")
        process.start(command)
    
    def runSimulation(self):
        if not self.unvFilePath:
            self.statusBar.showMessage("Erro: Nenhum arquivo UNV selecionado", 3000)
            return
        
        if not self.currentSolver:
            self.statusBar.showMessage("Erro: Nenhum solver selecionado", 3000)
            return
        
        self.statusBar.showMessage(f"Iniciando simulação com {self.currentSolver}...")
        command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && mpirun -np 6 {self.currentSolver} -parallel"'
        
        self.currentProcess = QProcess(self)
        self.setupProcessEnvironment(self.currentProcess)
        
        def finished(code):
            self.statusBar.showMessage(f"Simulação finalizada com código {code}", 5000)
            self.currentProcess = None
        
        self.currentProcess.finished.connect(finished)
        self.connectProcessSignals(self.currentProcess)
        self.outputArea.append(f"Comando executado: {command}")
        self.currentProcess.start(command)
    
    def reconstructPar(self):
        if not self.unvFilePath:
            self.statusBar.showMessage("Erro: Nenhum arquivo UNV selecionado", 3000)
            return
        
        self.statusBar.showMessage("Reconstruindo caso...")
        command = f'bash -l -c "source /opt/{self.currentOpenFOAMVersion}/etc/bashrc && reconstructPar"'
        
        self.currentProcess = QProcess(self)
        self.setupProcessEnvironment(self.currentProcess)
        
        def finished(code):
            self.statusBar.showMessage(f"Reconstrução finalizada com código {code}", 5000)
            self.currentProcess = None
        
        self.currentProcess.finished.connect(finished)
        self.connectProcessSignals(self.currentProcess)
        self.outputArea.append(f"Comando executado: {command}")
        self.currentProcess.start(command)
    
    def decomposePar(self):
        if not self.unvFilePath:
            self.statusBar.showMessage("Erro: Nenhum arquivo UNV selecionado", 3000)
            return
        
        self.statusBar.showMessage("Executando decomposePar...")
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
            self.statusBar.showMessage("Pastas de tempo reconstruídas removidas.", 3000)
        else:
            self.statusBar.showMessage("Nenhuma pasta de tempo encontrada.", 3000)
    
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
            self.statusBar.showMessage("Pastas de decomposição removidas.", 3000)
        else:
            self.statusBar.showMessage("Nenhuma pasta de decomposição encontrada.", 3000)
    
    def stopSimulation(self):
        if self.currentProcess and self.currentProcess.state() == QProcess.Running:
            self.currentProcess.terminate()
            self.statusBar.showMessage("Simulação interrompida", 3000)
        else:
            self.statusBar.showMessage("Nenhuma simulação em execução", 3000)
    
    def clearTerminal(self):
        self.outputArea.clear()
        self.statusBar.showMessage("Terminal limpo", 2000)
    
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
            self.statusBar.showMessage(f"Comando executado: {firstWord}", 2000)
    
    def setupProcessEnvironment(self, process):
        env = QProcessEnvironment.systemEnvironment()
        env.insert("FOAM_RUN", f"/opt/{self.currentOpenFOAMVersion}")
        process.setProcessEnvironment(env)
    
    def connectProcessSignals(self, process):
        def readOutput():
            self.outputArea.append(str(process.readAllStandardOutput(), 'utf-8'))
        
        def readError():
            self.outputArea.append(str(process.readAllStandardError(), 'utf-8'))
        
        def handleError(error):
            self.statusBar.showMessage(f"Erro no processo: {error}", 5000)
        
        process.readyReadStandardOutput.connect(readOutput)
        process.readyReadStandardError.connect(readError)
        process.errorOccurred.connect(handleError)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    interface = OpenFOAMInterface()
    interface.show()
    
    sys.exit(app.exec_())
