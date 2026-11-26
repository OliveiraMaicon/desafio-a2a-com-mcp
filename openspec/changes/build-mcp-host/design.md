# Design

## Context

Ver `proposal.md` e `specs/mcp-host/spec.md`. Pré-requisito: `implement-secure-mrtr` implementada e servidor MCP passando nos testes diretos. O SDK Python documenta `client.session.call_tool(..., allow_input_required=True)` como caminho manual, separado do cliente de alto nível que resolve perguntas automaticamente.

## Goals / Non-Goals

**Goals:** isolar transporte e continuação MCP em um adaptador pequeno reutilizável pelo futuro executor A2A.

**Non-Goals:** implementar A2A, duplicar schemas de tools, introduzir uma arquitetura genérica de agentes ou tomar decisões de domínio no host.

## Decisions

### API de início e retomada sem loop automático

Propor `agente/mcp_host.py` com duas operações conceituais: iniciar uma chamada e retomar uma continuação. Retornar resultado completo ou uma estrutura privada pendente com nome, cópia dos argumentos originais, chave/pergunta, alternativas, token intacto e contexto de trace. Esses nomes são desenho interno, não parte da API pública.

Não usar `Client.call_tool` de alto nível quando ele fecha o loop automaticamente. Usar a sessão manual com `allow_input_required=True` em todas as pernas. O host não fica em loop esperando entrada; retorna assim que o MCP pede informação.

### Anúncio de capability sem resposta humana automática

Na documentação atual, o SDK deriva elicitation.form do registro de um callback e sobrescreve campos reservados de `_meta`. Por isso, não basta adicionar capabilities manualmente em um dicionário por request. Configurar a capability pela API pública da versão travada; se ela exigir callback, registrar um guard que falhe caso seja chamado, e usar somente a API manual para receber input_required cru.

O guard não pode devolver accept, decline ou escolher sala. Um teste com contador prova zero invocações e zero retries espontâneos. Se a versão oferece configuração explícita de capabilities desacoplada de callback, preferi-la. Ambas as opções mantêm o mesmo desenho: o usuário da camada superior decide e o SDK não fecha a pergunta.

### Descoberta e contexto reutilizáveis, sem sessão de protocolo

Manter um cliente/transport vivo é aceitável; negociar estado de protocolo por conexão não é. Fazer descoberta preguiçosa antes da primeira tool, validar a tool encontrada e ler o resource. Um cache de catálogo/política pertence à aplicação, não substitui metadados por request. Recomeçar a descoberta após reconexão quando necessário.

O host conhece a intenção de chamar reservar_sala, mas deve conferir sua disponibilidade e schema descoberto em runtime. Falta da tool ou versão da política ilegível gera falha clara, não fallback hardcoded.

### Trace explícito e retorno opaco

Passar contexto de trace por operação, não em variável global ou headers mutáveis compartilhados. A propagação mais simples preserva o traceparent inteiro; gerar novos span-ids não é necessário para o desafio. O SDK gerencia ids JSON-RPC novos; testes capturam os ids para provar a propriedade.

Guardar requestState como string e nunca tentar decodificá-lo, ainda que seja base64 legível. Tratar enum e const do schema recebido sem consultar capacidade de sala. Preservar erro de execução e erro de protocolo como categorias diferentes para a futura tradução em Task.

## Risks / Trade-offs

- [Callback habilitado fecha MRTR sem a ponte] -> API manual obrigatória e teste de callback não invocado.
- [SDK ignora override de clientCapabilities] -> configurar pela API oficial e inspecionar requests reais no teste.
- [Trace de uma Task contamina outra] -> contexto imutável por operação e testes intercalados com trace-ids distintos.
- [Cache é confundido com sessão] -> conferir metadados e headers em cada request capturado, inclusive retry e resource.
- [Adaptador começa a conhecer regras de sala] -> testes só usam alternativas recebidas e não importam domínio do servidor.

## Migration Plan

Acrescentar o adaptador e um teste/script de exercício manual fora das pastas imutáveis, sem expor outro serviço ainda. O teste inicia MCP separado ou usa transporte HTTP de teste fiel. O caminho livre, aceitação e recusa devem funcionar sem A2A. Próxima etapa: `expose-a2a-tasks`.

## References

- `https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/handlers/multi-round-trip.md`
- `https://github.com/modelcontextprotocol/python-sdk/blob/main/src/mcp/client/session.py`
- Os nomes públicos citados são evidência de documentação atual, a conferir na versão exata instalada.
