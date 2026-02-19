# Guia de Código — Interface OpenFOAM

Objetivo
- Refatoração para facilitar leitura, manutenção e para que agentes/IA possam estender o projeto.

Estrutura atual
- main.py — ponto de entrada (cria QApplication e instancia `MainWindow`).
- main_window.py — contém a UI principal e lógica da janela (menus, ações, integração com o sistema de arquivos).
- editor.py — novo módulo responsável pelo editor de código (`CodeEditor`) e realce sintático (`SimpleHighlighter`).

Sobre a refatoração
- Separação de responsabilidades:
  - `editor.py` concentra toda a lógica do editor (numeração de linhas, seleção de linha atual, eventos de rolagem) e o realce sintático.
  - `main_window.py` fica responsável apenas pela construção da interface, menus, conexão com o `QProcess` e ações do usuário.
- Benefícios para agentes/IA:
  - Módulos menores e com responsabilidade única facilitam a geração de código automatizada.
  - Nomes claros (`CodeEditor`, `SimpleHighlighter`, `MainWindow`) simplificam buscas e modificações programáticas.

Como estender
- Adicionar novas regras de realce:
  - Editar `editor.py` em `SimpleHighlighter` e adicionar `QRegularExpression` + `QTextCharFormat`.
- Adicionar comandos ao menu "Comandos":
  - Em `main_window.py` localizar `comandos_menu = menubar.addMenu("Comandos")` e adicionar `QAction` com `triggered.connect` para a função desejada.
- Conectar ferramentas externas (e.g., OpenFOAM):
  - Use `self.process.start(<comando>)` no `MainWindow` e capture saída via `handle_stdout`/`handle_stderr`.

Recomendações para a IA ao gerar novo código
- Evitar mudanças que quebrem as assinaturas públicas (`MainWindow` construtor, `CodeEditor` API).
- Preferir adicionar funções utilitárias em novos módulos (por exemplo `io_helpers.py`) em vez de alterar arquivos grandes.
- Seguir o estilo existente: nomes em inglês para classes e métodos, mensagens em português na UI.

Teste rápido local
1. Instale dependências:

```bash
pip install PySide6
```

2. Execute a aplicação:

```bash
python main.py
```

Checklist para PR/commits
- [ ] Código passa lint básico (flake8/black opcional).
- [ ] Não quebrar `main.py` como ponto de entrada.
- [ ] Documentar mudanças importantes neste `CODE_GUIDE.md`.

---
Se quiser, eu posso:
- dividir `main_window.py` em mais módulos (menus, handlers, filebrowser),
- adicionar testes mínimos ou um `requirements.txt`.
