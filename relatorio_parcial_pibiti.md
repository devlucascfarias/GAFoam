# Relatório Parcial PIBITI (2025-2026)

## Identificação do Projeto
- **Projeto de Pesquisa:** PVIF4087-2025 - Simulação Computacional de Escoamento Multifásico de Meios Densos
- **Título do Plano:** Desenvolvimento de um Sistema Computacional para Controle e Análise de Simulações Multifásicas
- **Discente:** 23112117 - Lucas Correia Farias Porongaba
- **Orientador:** Glauber Jose Ferreira Tomaz da Silva
- **Instituição:** Universidade Federal de Alagoas (UFAL) - Instituto de Física
- **Período da bolsa:** 01/09/2025 a 31/08/2026
- **Status do plano:** Em andamento

## 1) Atividades Realizadas
No período referente ao relatório parcial, foram desenvolvidas atividades de levantamento técnico, arquitetura inicial e implementação do núcleo da interface gráfica para uso com OpenFOAM em ambiente local.

As principais entregas realizadas foram:

1. Estruturação da aplicação desktop em Python com PySide6, incluindo janela principal, organização de painéis e fluxo de uso por caso de simulação.
2. Implementação de explorador de arquivos do caso OpenFOAM, com abertura da pasta de trabalho e validação da estrutura mínima (`0`, `constant`, `system`).
3. Desenvolvimento de editor integrado para arquivos de caso, com abas, numeração de linhas, destaque de sintaxe para dicionários OpenFOAM e operações de edição/salvamento.
4. Implementação de terminal embutido para execução de comandos e acompanhamento de saídas diretamente na interface.
5. Implementação de rotinas de execução dos comandos de malha (`blockMesh`, `checkMesh`, `snappyHexMesh`) pelo próprio sistema.
6. Implementação de execução de simulação via `Allrun`, incluindo criação automática do script quando ausente, controle de permissões, monitoramento e botão de parada.
7. Desenvolvimento de painel de logs e monitoramento, com leitura contínua de arquivos de saída do solver e atualização em tempo quase real.
8. Implementação de parser de métricas da simulação para extração de resíduos e variáveis de acompanhamento (ex.: residual inicial por variável, `Courant Number`, `deltaT`, estatísticas de `y+`, além de grandezas customizadas quando presentes no log).
9. Implementação de módulo gráfico de resíduos com Matplotlib, com histórico temporal, seleção de escala linear/logarítmica e limpeza de séries.
10. Implementação de visualização de malhas STL em 3D com PyVista/PyVistaQt, integrada ao fluxo de navegação por arquivos.
11. Organização inicial do código em módulos (janela principal, editor, terminal, browser, handlers), visando manutenção e evolução da plataforma.

## 2) Comparação entre o Plano Original e o Executado
De modo geral, o cronograma foi seguido de forma satisfatória para a etapa parcial.

1. **Levantamento de requisitos e estudo técnico do OpenFOAM/AWS:**
Foi executado para definição do escopo inicial da interface e priorização das funcionalidades essenciais para operação local.

2. **Projeto e desenvolvimento da GUI:**
Foi a frente com maior avanço até o momento. O núcleo funcional da interface foi implementado e já permite configurar/editar casos e executar etapas relevantes do fluxo OpenFOAM local.

3. **Módulos de integração com OpenFOAM:**
Foram parcialmente concluídos no escopo local (execução de comandos, leitura de logs e análise de resíduos). A validação com múltiplos casos segue em andamento.

4. **Integração com AWS (EC2/S3/Batch):**
Esta etapa encontra-se iniciada em nível de planejamento técnico e definição de estratégia de integração, porém ainda não concluída nesta fase parcial. O foco inicial foi consolidar primeiro a base local da plataforma.

5. **Visualização e monitoramento de variáveis:**
Foi implementado um módulo funcional de monitoramento por logs e gráficos, alinhado ao objetivo de acompanhar estabilidade e evolução da simulação.

6. **Documentação e materiais de apoio:**
Há documentação técnica inicial do código e da estrutura da aplicação. A produção de manuais e tutoriais completos está prevista para a próxima fase.

Em síntese, houve aderência ao plano com priorização técnica coerente: primeiro consolidar a base de execução local e, em seguida, expandir para a camada de nuvem.

## 3) Outras Atividades Desenvolvidas
Além do escopo principal, também foram realizadas atividades complementares importantes para robustez do projeto:

1. Refinamento da usabilidade da interface (barra de ferramentas, atalhos, organização em abas e feedback de estado da execução).
2. Implementação de mecanismos de controle de processo para evitar concorrência indevida de execuções e permitir parada segura de jobs.
3. Melhoria da resiliência do sistema para lidar com diferentes formatos de saída e cenários de falha de leitura.
4. Estruturação inicial para modularização futura (facilitando inserção de novos módulos e integração com serviços externos).

## 4) Resultados Preliminares
Os resultados preliminares indicam viabilidade técnica da proposta.

1. Foi obtido um protótipo funcional capaz de centralizar em uma única interface tarefas que normalmente exigem múltiplas ferramentas e uso intensivo de terminal.
2. O sistema já reduz a barreira operacional para configuração e execução de casos OpenFOAM em ambiente local.
3. O monitoramento de resíduos e métricas de estabilidade diretamente na GUI mostrou-se útil para acompanhamento rápido da convergência.
4. A visualização de STL e a edição integrada de arquivos de caso melhoraram o fluxo de preparação e inspeção das simulações.
5. A arquitetura implementada permite evolução incremental para integração com AWS, sem necessidade de reescrever o núcleo da aplicação.

Portanto, nesta etapa parcial, o projeto apresenta evolução consistente com os objetivos de iniciação tecnológica, com entregas concretas de software e base sólida para a fase de integração em nuvem e validação ampliada.

## 5) Dificuldades Encontradas e Ajustes
1. A principal dificuldade técnica foi lidar com a heterogeneidade dos logs de diferentes solucionadores e configurações de execução, exigindo regras de parsing mais flexíveis.
2. Houve necessidade de priorizar a estabilidade do fluxo local antes da integração com AWS para reduzir riscos de retrabalho.
3. Dependências gráficas e de visualização 3D demandaram ajustes de compatibilidade de ambiente.

Como ajuste de execução, adotou-se a estratégia de desenvolvimento em camadas:
- Primeiro: núcleo local estável (editor + execução + monitoramento).
- Segundo: integração com serviços de nuvem e automação de submissão de jobs.

## 6) Próximas Etapas (até o relatório final)
1. Concluir o módulo de integração com AWS (submissão, monitoramento e recuperação de resultados).
2. Ampliar os testes com diferentes solucionadores multifásicos (ex.: `interFoam`, `multiphaseInterFoam`, `incompressibleDenseParticleFoam`).
3. Integrar melhor a etapa de pós-processamento e visualização de resultados.
4. Consolidar documentação de usuário (manual rápido e tutorial de uso).
5. Preparar material para disseminação dos resultados (resumo técnico, apresentação e base para artigo).

## Texto Curto para Colar no SIGAA (resumo pronto)
Durante o período parcial do PIBITI, foi desenvolvido um protótipo funcional de interface gráfica em Python/PySide6 para gerenciamento de simulações OpenFOAM. A aplicação já permite abertura e validação de casos, edição de arquivos com destaque de sintaxe, execução de comandos de malha (blockMesh, checkMesh, snappyHexMesh), execução via Allrun e monitoramento de logs com análise de resíduos e variáveis de estabilidade (como Courant Number, deltaT e y+). Também foi integrado visualizador 3D de arquivos STL e painel gráfico de resíduos em tempo quase real. Em comparação ao plano original, houve bom avanço na etapa de desenvolvimento da GUI e da integração local com OpenFOAM. A integração com AWS foi iniciada em planejamento técnico e será consolidada na próxima fase, após estabilização do núcleo local. Os resultados preliminares indicam viabilidade da proposta e redução da complexidade operacional para usuários não especialistas.
