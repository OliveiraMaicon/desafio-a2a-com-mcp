# Tasks

## 1. Pré-requisito e aplicação oficial A2A

- [ ] 1.1 Confirmar build-mcp-host implementada com sua integração passando; instalar e fixar versão exata do SDK oficial A2A Python compatível com JSON-RPC v1.0, verificando imports e instalação conjunta com MCP sem dependência de LLM.
- [ ] 1.2 Criar aplicação/entrypoint em agente/ para um worker na porta 7300 com endpoint /a2a; testar SendMessage/GetTask no binding v1.0 e documentar no entrypoint a separação entre os dois processos.
- [ ] 1.3 Publicar card válido no well-known com supportedInterfaces, protocolBinding JSONRPC, protocolVersion 1.0 e skill reservar-sala; testar HTTP 200, URL efetiva, modos de texto e capabilities sem streaming/push.

## 2. Parser, executor e Task pública

- [ ] 2.1 Implementar parser da gramática fixa sem catálogo local de salas ou LLM; testar pedido válido, responsável preservado e entrada malformada com erro controlado, documentando o formato aceito junto ao parser.
- [ ] 2.2 Criar Task com id/contextId próprios e histórico da mensagem do usuário; testar transições SUBMITTED e WORKING antes de aguardar o MCP e consultar estado corrente com GetTask durante I/O atrasado controladamente.
- [ ] 2.3 Configurar store oficial em memória com serialização restrita aos campos públicos; testar GetTask com id, contextId, status, histórico e artifacts e documentar a perda intencional de Tasks após restart do agente.
- [ ] 2.4 Encaminhar traceparent do contexto HTTP ao executor/host sem variável global; testar que chamadas MCP originadas de SendMessage preservam o trace-id, inclusive com duas operações intercaladas.

## 3. Resultados completos e terminalidade

- [ ] 3.1 Traduzir reserva livre para COMPLETED e artifact reserva com identidade e JSON dos campos exigidos; testar SendMessage/GetTask e verificar que politica vem da leitura do resource pelo host.
- [ ] 3.2 Traduzir isError da tool para FAILED com mensagem exata no status e histórico, e falhas de protocolo/transporte para mensagem segura; testar sala-delorean e indisponibilidade MCP sem artifact de sucesso ou vazamento de estruturas privadas.
- [ ] 3.3 Recusar SendMessage em Task COMPLETED, FAILED ou CANCELED; testar preservação do estado e ausência de novo tools/call, usando fixture própria para o estado CANCELED enquanto a ponte ainda não foi implementada.
- [ ] 3.4 Manter o branch de continuação explicitamente reservado à próxima change sem resolver elicitation automaticamente; testar que resultado pendente do host não cria reserva fictícia nem aciona callback, documentando o limite intermediário do executor.

## 4. Gate da etapa

- [ ] 4.1 Executar regressão do host e integração A2A de card, reserva livre, GetTask, sala inexistente e estado terminal com processos separados; verificar envelopes v1.0 contra os exemplos sem esperar ainda os cenários de ponte do validador.
