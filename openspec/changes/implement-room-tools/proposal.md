# Proposal

## Why

Com a fronteira MCP estabelecida, o servidor precisa responder de forma determinística às consultas e reservas válidas. Concentrar as poucas regras no servidor evita que o futuro agente replique decisões de domínio.

## What Changes

- Acrescentar `consultar_disponibilidade` e `reservar_sala` à descoberta MCP.
- Carregar reservas iniciais dos JSONs e manter novas reservas em memória, sem gravar no starter.
- Aplicar as mesmas validações de sala, intervalo, janela e duração nas duas tools.
- Retornar erros de execução com as mensagens exatas e resultados bem-sucedidos com `structuredContent` e JSON em texto.
- Criar reservas livres com identificador próprio e versão da política.
- Preparar cálculo de conflitos e alternativas para a change de MRTR, sem elicitation nesta etapa.

## Capabilities

### New Capabilities

- `room-tools`: consulta de disponibilidade, regras de uso e criação de reservas livres via MCP.

### Modified Capabilities

Nenhuma. A capability `mcp-transport` da change anterior permanece válida; sua descoberta passa a incluir as novas tools.

## Impact

- Áreas previstas: `servidor-mcp/` e testes próprios de domínio e HTTP em `tests/`.
- Etapa 2 de 7; aplicar depois de `establish-mcp-transport`. Próxima: `implement-secure-mrtr`.
- Dados e política existentes são somente leitura; reservas criadas não sobrevivem ao restart.
- O caminho de conflito ainda não está completo: não criar reserva sobreposta nem simular sucesso; o ciclo obrigatório de escolha é responsabilidade da próxima change.
- Sem ORM, banco, camada de serviços genérica, regra baseada na data atual ou mudanças no agente.
