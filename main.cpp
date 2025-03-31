#include <QApplication>
#include <QWidget>
#include <QPushButton>
#include <QVBoxLayout>
#include <QFileDialog>
#include <QTextEdit>
#include <QProcess>
#include <QDebug>
#include <QFile>
#include <QTextStream>
#include <QHBoxLayout>
#include <QLabel>
#include <QMenuBar>
#include <QMenu>
#include <QAction>
#include <QLineEdit>
#include <QStatusBar>
#include <QTimer>
#include <QSysInfo>
#include <QStorageInfo>

class OpenFOAMInterface : public QWidget
{
    Q_OBJECT

public:
    OpenFOAMInterface(QWidget *parent = nullptr) : QWidget(parent)
    {
        setWindowTitle("GAFoam");
        resize(1000, 600);

        // Layout principal
        QVBoxLayout *mainVerticalLayout = new QVBoxLayout(this);
        mainVerticalLayout->setContentsMargins(5, 5, 5, 5);

        // Barra de menu
        setupMenuBar(mainVerticalLayout);

        // Área principal (terminal + editor)
        setupMainContentArea(mainVerticalLayout);

        // Barra de status
        setupStatusBar(mainVerticalLayout);

        // Timer para atualizar os indicadores de sistema
        QTimer *systemMonitorTimer = new QTimer(this);
        connect(systemMonitorTimer, &QTimer::timeout, this, &OpenFOAMInterface::updateSystemUsage);
        systemMonitorTimer->start(2000); // Atualizar a cada 2 segundos

        setLayout(mainVerticalLayout);
    }

private:
    void setupMenuBar(QVBoxLayout *mainLayout)
    {
        QMenuBar *menuBar = new QMenuBar(this);
        QMenu *fileMenu = new QMenu("Arquivo", menuBar);
        QMenu *terminalMenu = new QMenu("Terminal", menuBar);

        QAction *checkMeshAction = new QAction("Checar Malha", this);
        QAction *importUNVAction = new QAction("Importar Arquivo (.unv)", this);
        QAction *clearTerminalAction = new QAction("Limpar Terminal", this);

        fileMenu->addAction(checkMeshAction);
        fileMenu->addAction(importUNVAction);
        terminalMenu->addAction(clearTerminalAction);

        menuBar->addMenu(fileMenu);
        menuBar->addMenu(terminalMenu);
        mainLayout->setMenuBar(menuBar);

        connect(checkMeshAction, &QAction::triggered, this, &OpenFOAMInterface::checkMesh);
        connect(importUNVAction, &QAction::triggered, this, &OpenFOAMInterface::chooseUNV);
        connect(clearTerminalAction, &QAction::triggered, this, &OpenFOAMInterface::clearTerminal);
    }

    void setupMainContentArea(QVBoxLayout *mainLayout)
    {
        QHBoxLayout *contentLayout = new QHBoxLayout();

        // Área do terminal
        QVBoxLayout *terminalLayout = new QVBoxLayout();
        terminalLayout->addWidget(new QLabel("Terminal e Logs", this));

        outputArea = new QTextEdit(this);
        outputArea->setReadOnly(true);
        terminalLayout->addWidget(outputArea);

        terminalInput = new QLineEdit(this);
        terminalInput->setPlaceholderText(">>");
        terminalLayout->addWidget(terminalInput);

        QPushButton *runButton = new QPushButton("Rodar Simulação", this);
        QPushButton *stopButton = new QPushButton("Parar Simulação", this);
        terminalLayout->addWidget(runButton);
        terminalLayout->addWidget(stopButton);

        // Área do editor
        QVBoxLayout *editorLayout = new QVBoxLayout();
        editorLayout->addWidget(new QLabel("Editor de Arquivo", this));

        fileEditor = new QTextEdit(this);
        editorLayout->addWidget(fileEditor);

        QPushButton *editButton = new QPushButton("Editar Arquivo", this);
        QPushButton *saveButton = new QPushButton("Salvar Arquivo", this);
        editorLayout->addWidget(editButton);
        editorLayout->addWidget(saveButton);

        // Adicionar à área principal
        contentLayout->addLayout(terminalLayout, 1);
        contentLayout->addLayout(editorLayout, 1);
        mainLayout->addLayout(contentLayout, 1);

        // Conexões
        connect(runButton, &QPushButton::clicked, this, &OpenFOAMInterface::runSimulation);
        connect(stopButton, &QPushButton::clicked, this, &OpenFOAMInterface::stopSimulation);
        connect(editButton, &QPushButton::clicked, this, &OpenFOAMInterface::editFile);
        connect(saveButton, &QPushButton::clicked, this, &OpenFOAMInterface::saveFile);
        connect(terminalInput, &QLineEdit::returnPressed, this, &OpenFOAMInterface::executeTerminalCommand);
    }

    void setupStatusBar(QVBoxLayout *mainLayout)
    {
        statusBar = new QStatusBar(this);

        // Labels permanentes
        meshPathLabel = new QLabel("Malha: Nenhuma", statusBar);
        cpuUsageLabel = new QLabel("CPU: --%", statusBar);
        memUsageLabel = new QLabel("Memória: --%", statusBar);

        statusBar->addPermanentWidget(meshPathLabel, 1);
        statusBar->addPermanentWidget(cpuUsageLabel);
        statusBar->addPermanentWidget(memUsageLabel);

        mainLayout->addWidget(statusBar);
    }

    void updateSystemUsage()
    {
        // Obter uso de CPU (simplificado)
        static qint64 lastIdle = 0, lastTotal = 0;

        QFile file("/proc/stat");
        if (file.open(QIODevice::ReadOnly)) {
            QTextStream in(&file);
            QString line = in.readLine();
            QStringList values = line.split(' ', QString::SkipEmptyParts);
            if (values.size() > 4) {
                qint64 user = values[1].toLongLong();
                qint64 nice = values[2].toLongLong();
                qint64 system = values[3].toLongLong();
                qint64 idle = values[4].toLongLong();

                qint64 total = user + nice + system + idle;
                qint64 deltaTotal = total - lastTotal;
                qint64 deltaIdle = idle - lastIdle;

                if (deltaTotal > 0 && lastTotal > 0) {
                    int cpuUsage = 100 * (deltaTotal - deltaIdle) / deltaTotal;
                    cpuUsageLabel->setText(QString("CPU: %1%").arg(cpuUsage));
                }

                lastTotal = total;
                lastIdle = idle;
            }
            file.close();
        }

        // Obter uso de memória
        QStorageInfo storage = QStorageInfo::root();
        double memUsed = (storage.bytesTotal() - storage.bytesFree()) / (1024.0 * 1024.0 * 1024.0);
        double memTotal = storage.bytesTotal() / (1024.0 * 1024.0 * 1024.0);
        int memPercent = (memUsed / memTotal) * 100;

        memUsageLabel->setText(QString("Memória: %1% (%2G/%3G)")
                              .arg(memPercent)
                              .arg(memUsed, 0, 'f', 1)
                              .arg(memTotal, 0, 'f', 1));
    }

private slots:
    void chooseUNV()
    {
        QString fileName = QFileDialog::getOpenFileName(this, "Escolher Arquivo UNV", "", "Arquivos UNV (*.unv)");
        if (!fileName.isEmpty()) {
            unvFilePath = fileName;
            outputArea->append("Arquivo UNV escolhido: " + fileName);
            meshPathLabel->setText("Malha: " + QFileInfo(fileName).fileName());
            statusBar->showMessage("Malha carregada com sucesso", 3000);
        }
    }

    void checkMesh()
    {
        if (unvFilePath.isEmpty()) {
            statusBar->showMessage("Erro: Nenhum arquivo UNV selecionado", 3000);
            return;
        }

        statusBar->showMessage("Executando checkMesh...");

        QString command = QString("bash -l -c \"source /opt/openfoam9/etc/bashrc && ideasUnvToFoam %1 && blockMesh && checkMesh\"")
                          .arg(unvFilePath);

        QProcess *process = new QProcess(this);
        setupProcessEnvironment(process);

        connectProcessSignals(process);
        outputArea->append("Comando executado: " + command);
        process->start(command);
    }

    void runSimulation()
    {
        if (unvFilePath.isEmpty()) {
            statusBar->showMessage("Erro: Nenhum arquivo UNV selecionado", 3000);
            return;
        }

        statusBar->showMessage("Iniciando simulação...");

        QString command = QString("bash -l -c \"source /opt/openfoam9/etc/bashrc && ideasUnvToFoam %1 && blockMesh && twoLiquidMixingFoam\"")
                          .arg(unvFilePath);

        currentProcess = new QProcess(this);
        setupProcessEnvironment(currentProcess);

        connect(currentProcess, QOverload<int>::of(&QProcess::finished),
                [this](int code) {
                    statusBar->showMessage(QString("Simulação finalizada com código %1").arg(code), 5000);
                    currentProcess = nullptr;
                });

        connectProcessSignals(currentProcess);
        outputArea->append("Comando executado: " + command);
        currentProcess->start(command);
    }

    void stopSimulation()
    {
        if (currentProcess && currentProcess->state() == QProcess::Running) {
            currentProcess->terminate();
            statusBar->showMessage("Simulação interrompida", 3000);
        } else {
            statusBar->showMessage("Nenhuma simulação em execução", 3000);
        }
    }

    void clearTerminal()
    {
        outputArea->clear();
        statusBar->showMessage("Terminal limpo", 2000);
    }

    void editFile()
    {
        // Especificar o diretório 'system' onde os arquivos de configuração estão localizados
        QString systemDir = "/home/gaf/build-GAFoam-Desktop-Debug/system";  // Ajuste conforme o seu caminho

        // Debug: Verificar o diretório
        qDebug() << "Diretório escolhido: " << systemDir;

        // Diálogo para escolher arquivo, filtro mais amplo para arquivos de código-fonte
        QString fileName = QFileDialog::getOpenFileName(this, "Escolher Arquivo de Código", systemDir, "Todos os Arquivos (*);;Arquivos de Código (*.dict *.txt *.swp)");

        // Verificar se o arquivo foi selecionado
        if (!fileName.isEmpty()) {
            qDebug() << "Arquivo selecionado: " << fileName;

            QFile file(fileName);
            if (file.open(QIODevice::ReadOnly | QIODevice::Text)) {
                QTextStream in(&file);
                QString fileContent = in.readAll();
                fileEditor->setPlainText(fileContent);
                file.close();

                // Guardar o caminho do arquivo para salvar depois
                currentFilePath = fileName;
                outputArea->append("Arquivo de código aberto: " + fileName);
            } else {
                outputArea->append("Erro ao abrir o arquivo para edição.");
            }
        } else {
            outputArea->append("Nenhum arquivo selecionado.");
        }
    }

    void saveFile()
    {
        if (currentFilePath.isEmpty()) {
            outputArea->append("Nenhum arquivo carregado para salvar.");
            return;
        }

        QFile file(currentFilePath);
        if (file.open(QIODevice::WriteOnly | QIODevice::Text)) {
            QTextStream out(&file);
            out << fileEditor->toPlainText();
            file.close();
            outputArea->append("Arquivo salvo com sucesso: " + currentFilePath);
        } else {
            outputArea->append("Erro ao salvar o arquivo.");
        }
    }

    void executeTerminalCommand()
    {
        QString command = terminalInput->text();
        if (!command.isEmpty()) {
            outputArea->append("> " + command);
            terminalInput->clear();

            QProcess *process = new QProcess(this);
            setupProcessEnvironment(process);

            connectProcessSignals(process);
            process->start("bash", QStringList() << "-l" << "-c" << "source /opt/openfoam9/etc/bashrc && " + command);

            statusBar->showMessage("Comando executado: " + command.split(' ').first(), 2000);
        }
    }

private:
    void setupProcessEnvironment(QProcess *process)
    {
        QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
        env.insert("FOAM_RUN", "/opt/OpenFOAM/OpenFOAM-9");
        process->setProcessEnvironment(env);
    }

    void connectProcessSignals(QProcess *process)
    {
        connect(process, &QProcess::readyReadStandardOutput, this, [=]() {
            outputArea->append(process->readAllStandardOutput());
        });

        connect(process, &QProcess::readyReadStandardError, this, [=]() {
            outputArea->append(process->readAllStandardError());
        });

        connect(process, &QProcess::errorOccurred, this, [=](QProcess::ProcessError error) {
            statusBar->showMessage("Erro no processo: " + QString::number(error), 5000);
        });
    }

    // Membros da classe
    QTextEdit *outputArea;
    QTextEdit *fileEditor;
    QLineEdit *terminalInput;
    QStatusBar *statusBar;
    QLabel *meshPathLabel;
    QLabel *cpuUsageLabel;
    QLabel *memUsageLabel;

    QString unvFilePath;
    QString currentFilePath;
    QProcess *currentProcess = nullptr;
};

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);

    // Definir estilo visual mais moderno
    app.setStyle("Fusion");

    OpenFOAMInterface interface;
    interface.show();

    return app.exec();
}

#include "main.moc"
