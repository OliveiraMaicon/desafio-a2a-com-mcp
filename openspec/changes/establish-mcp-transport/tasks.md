# Tasks

## 1. Ambiente e compatibilidade do SDK

- [ ] 1.1 Conferir na distribuição Python escolhida do SDK MCP v2 as APIs modernas de servidor, transporte stateless, MRTR e segurança de requestState; verificar a existência dos símbolos e registrar versão e evidência nas notas técnicas da implementação, sem substituir protocolo por código próprio.
- [ ] 1.2 Criar `pyproject.toml` na raiz e lock com versões exatas de dependências diretas, configuração de testes e mínimo real de Python; verificar instalação em ambiente virtual novo e imports necessários, sem SDK de provedor de LLM.
- [ ] 1.3 Criar entrypoint fino em `servidor-mcp/` e carregamento de caminhos relativo ao projeto; verificar que o processo sobe na porta 7301 a partir dos comandos de desenvolvimento e não depende do cwd para encontrar `dados/`.

## 2. Transporte, validação e observabilidade

- [ ] 2.1 Configurar `/mcp` no modo moderno stateless com respostas JSON; adicionar teste HTTP que envia tools/list sem initialize e verifica HTTP 200, envelope JSON-RPC e resultType complete.
- [ ] 2.2 Garantir rejeição de `_meta` sem protocolVersion ou clientCapabilities; adicionar testes para ambos os casos, inclusive após request válido, verificando `-32602`, HTTP 400 e preservação de id.
- [ ] 2.3 Garantir conferência dos headers de versão, método e nome contra o corpo; adicionar testes de divergência verificando `-32020` e ausência de execução da operação.
- [ ] 2.4 Registrar em stderr método, id e traceparent sem corpo integral; adicionar testes de request válido e rejeitado e documentar o formato do log junto ao entrypoint, verificando que o transporte ainda recebe o corpo intacto.

## 3. Listagem e resource

- [ ] 3.1 Declarar capabilities tools/resources e registrar listar_salas com inputSchema de objeto e outputSchema; verificar descoberta HTTP e validade do JSON Schema, sem fixar que o catálogo sempre terá só uma tool.
- [ ] 3.2 Implementar listar_salas a partir do JSON somente leitura; testar as cinco salas, conformidade com outputSchema e igualdade entre structuredContent e JSON do texto, documentando o contrato no módulo.
- [ ] 3.3 Registrar politica://uso com texto integral e text/markdown; testar igualdade com o arquivo, primeira linha de versão e `-32602` para URI inexistente.
- [ ] 3.4 Garantir rejeição de tool inexistente; testar `-32602` ou isError verdadeiro sem sucesso aparente.

## 4. Gate da etapa

- [ ] 4.1 Executar a suíte incremental do transporte e conferir por HTTP os exemplos wire 01 e 05; verificar que dados/, exemplos/ e validador/ permanecem inalterados e registrar que as outras duas tools pertencem à próxima change.
