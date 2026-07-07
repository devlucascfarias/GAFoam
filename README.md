# GAFoam Interface

Uma Interface Gráfica de Usuário (GUI) desktop moderna e intuitiva para o **OpenFOAM** (software de Dinâmica dos Fluidos Computacional - CFD). Desenvolvido em Python com a biblioteca **PySide6 (Qt)**, o sistema centraliza a configuração, execução e monitoramento de simulações CFD de forma integrada e automatizada.

Este projeto foi reestruturado para oferecer uma experiência de desenvolvimento limpa, com layouts dinâmicos e isolamento de processos interativos.

---

## 🚀 Principais Funcionalidades

* **Explorador de Casos**: Navegador de arquivos integrado que valida automaticamente a estrutura de diretórios obrigatória do OpenFOAM (`0/`, `constant/`, `system/`).
* **Editor de Caso Avançado**: Editor de texto integrado com numeração de linhas e realce de sintaxe robusto para dicionários do OpenFOAM, incluindo suporte completo para coloração de códigos C++ embutidos em blocos `#{ ... #}`.
* **Visualização de Malhas 3D**: Renderização e inspeção de geometrias STL integradas diretamente na janela principal através do PyVista.
* **Console de Execução**: Exibição limpa em tempo real de logs de execução para comandos de malha (`blockMesh`, `checkMesh`, `snappyHexMesh`) e scripts de inicialização, simulando linhas de comando (`$ command`).
* **Monitor de Simulação em Tempo Real**: 
  * Exibição contínua dos logs do solver do OpenFOAM com rolagem automática inteligente.
  * Gráfico de convergência de resíduos dinâmico desenvolvido em Matplotlib.
  * **Plotagem Flexível**: Permite visualizar a evolução dos resíduos tanto em função do número de **Iterações** quanto do **Tempo Físico de Simulação** (segundos).
* **Layout Dinâmico e Guiado**: 
  * O gráfico de resíduos divide a tela horizontalmente com o editor de código apenas durante a execução da simulação, maximizando o espaço de edição fora desse período.
  * Alternância automática de abas no painel inferior para focar na saída relevante conforme o comando disparado (Console vs. Simulação).

---

## 📁 Estrutura do Projeto

* [main.py](file:///home/reynolds-02/interface_openfoam/main.py): Ponto de entrada que instancia o `QApplication` e exibe a janela principal.
* [main_window.py](file:///home/reynolds-02/interface_openfoam/main_window.py): Lógica central do layout do aplicativo, gerenciamento de subprocessos (`QProcess`) e interação entre os painéis.
* [editor.py](file:///home/reynolds-02/interface_openfoam/editor.py): Implementação do editor de texto (`CodeEditor`) e do analisador de realce de sintaxe (`SimpleHighlighter`).
* [residuals.py](file:///home/reynolds-02/interface_openfoam/residuals.py): Widget gráfico com Matplotlib (`ResidualsWidget`) encarregado de processar e exibir os dados de convergência.
* [filebrowser.py](file:///home/reynolds-02/interface_openfoam/filebrowser.py): Gerenciador da árvore de arquivos e diretórios lateral.
* [stl_viewer.py](file:///home/reynolds-02/interface_openfoam/stl_viewer.py): Visualizador 3D para renderizar arquivos de geometria tridimensionais (STL).
* [menus.py](file:///home/reynolds-02/interface_openfoam/menus.py): Definição estrutural da barra de menus superior do aplicativo.
* [handlers.py](file:///home/reynolds-02/interface_openfoam/handlers.py): Encapsulamento de callbacks de leitura de saídas padrão (`stdout`/`stderr`) de subprocessos locais.

---

## 🛠️ Requisitos de Ambiente

Para rodar a aplicação localmente fora do ambiente virtual, você precisará do Python 3.12+ e das dependências gráficas instaladas no seu interpretador:

```bash
pip install PySide6 pyvista pyvistaqt numpy matplotlib QtPy vtk
```

---

## 💻 Como Executar

Execute o script principal utilizando o Python:

```bash
python3 main.py
```

> **Dica**: Se preferir utilizar o atalho simplificado `python main.py` e o seu sistema Linux não possuir o mapeamento, você pode criar um link simbólico definitivo rodando:
> ```bash
> sudo apt install python-is-python3
> ```

---

## ⚙️ Fluxo de Trabalho Recomendado

1. **Abrir o Caso**: Use o botão **Abrir Caso** na barra de ferramentas para selecionar o diretório contendo seu caso OpenFOAM.
2. **Editar Dicionários**: Dê duplo clique em qualquer arquivo (ex: `controlDict`, `fvSolution`) no navegador esquerdo para abri-lo no editor de abas.
3. **Gerar Malha**: Utilize os botões `blockMesh` e `snappyHexMesh` na barra de ferramentas. O console focará automaticamente para mostrar o progresso.
4. **Executar Simulação**: Clique no botão **Rodar** (ou `Ctrl + R`). A interface exibirá o gráfico de resíduos na parte superior e os logs detalhados na aba de simulação na parte inferior, mantendo-se atualizada passo a passo.
5. **Parar Execução**: Se a simulação divergir ou precisar ser abortada, utilize o botão **Parar** para encerrar o solver e todos os seus processos filhos de maneira limpa.
