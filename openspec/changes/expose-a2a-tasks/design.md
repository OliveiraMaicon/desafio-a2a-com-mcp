# Design

## Context

Ver `proposal.md` e `specs/a2a-tasks/spec.md`. Pré-requisito: `build-mcp-host` implementada. O usuário confirmou o SDK oficial A2A Python. A documentação de `a2aproject/a2a-python` v1.3.1 declara suporte a JSON-RPC v1.0 e armazenamento em memória; exemplos antigos v0.x possuem nomes incompatíveis com o starter.

## Goals / Non-Goals

**Goals:** usar infraestrutura oficial de Task e JSON-RPC mantendo a lógica de aplicação pequena e assíncrona.

**Non-Goals:** expor SSE, REST, gRPC ou push notifications; implementar parser de linguagem natural; concluir o caminho de conflito antes da change da ponte.

## Decisions

### SDK A2A v1.0, não dispatcher artesanal

Usar aplicação HTTP/ASGI, request handler, executor e armazenamento de Tasks do SDK oficial, com a interface JSON-RPC moderna explicitamente selecionada. Conferir a versão compatível com o ambiente e o MCP e fixá-la exatamente no pyproject/lock. A v1.3.1 é referência documental consultada, não substitui um teste de compatibilidade da distribuição instalada.

Publicar somente o binding necessário em `/a2a` e o card no well-known. Campos públicos e enumerações devem corresponder aos exemplos v1.0, mesmo se os tipos internos do SDK usarem nomes Python diferentes. Não preencher securitySchemes nem anunciar capabilities não implementadas.

### Estado público em memória, estado privado separado

Usar `InMemoryTaskStore` ou equivalente oficial para Task, histórico, status e artifacts. Não anexar tokens ou objetos internos a metadata, history ou status da Task. A change seguinte acrescentará um armazenamento separado de continuações, indexado por taskId.

Banco é alternativa rejeitada porque persistência de Tasks não é exigida. Rodar um único worker de agente evita que uma consulta caia em memória de outro processo; escalabilidade não é objetivo deste desafio.

### Executor assíncrono e parser restrito

Propor entrypoint fino, módulo de aplicação A2A e executor em `agente/`. Interpretar a gramática fixa, separando campos conhecidos sem fazer inferência de sala ou horário. Preservar o nome do responsável conforme o texto; nomes com espaços não devem ser cortados por um split ingênuo se puderem ser obtidos do último campo responsavel.

Atualizar SUBMITTED e WORKING antes de aguardar o host, sem prender GetTask em um lock durante I/O. Para teste, atrasar controladamente a resposta MCP e consultar a Task criada usando id capturado no store/fixture; não adicionar endpoint de debug público para isso.

Integrar neste passo somente resultado completo e erro. O branch de continuação fica reservado à próxima change, sem escolher sala automaticamente, manter request aberto ou apresentar conflito como sucesso. A conformidade A2A completa só é declarada depois da ponte.

### Produto e falhas sem acoplamento ao domínio

Montar artifact a partir da reserva devolvida pelo MCP e da versão lida pelo host no resource. O agente não lê arquivos de dados diretamente. Garantir que mensagens de erro da tool apareçam tanto no status quanto no histórico.

Aplicar a regra de terminalidade usando o handler/store oficial e guard adicional de aplicação quando necessário. Um erro de protocolo/transport do MCP resulta em falha segura da Task, sem vazar estruturas privadas ou token em traceback. Encaminhar o traceparent do contexto HTTP ao executor por contexto explícito, sem variável global.

## Risks / Trade-offs

- [Compatibilidade automática seleciona wire v0.x] -> testar supportedInterfaces, roles, métodos e estados exatos no endpoint v1.0.
- [Handler mantém lock durante chamada MCP] -> teste GetTask concorrente com tool atrasada.
- [Armazenamento público serializa estado extra] -> nunca guardar ali a continuação; testar a representação completa e erros.
- [Parser tenta validar sala localmente] -> encaminhar sala inexistente e provar que a mensagem vem da tool.
- [SDK limita versão mínima de Python] -> usar o mínimo real compatível e documentar no ambiente, sem presumir que o mínimo do validador é o mínimo da aplicação.

## Migration Plan

Adicionar o segundo processo em 7300 sem alterar o MCP em 7301. Executar testes de card, reserva livre, falha e terminalidade contra ambos os processos. Parar/reiniciar o agente descarta Tasks por desenho; não promete recuperação de Tasks após restart. Próxima etapa: `bridge-task-continuations`.

## References

- `https://github.com/a2aproject/a2a-python/blob/v1.3.1/README.md`
- `https://github.com/a2aproject/a2a-python/blob/v1.3.1/samples/README.md`
- Contratos locais: wire 07–10 e verificações A2A do validador.
