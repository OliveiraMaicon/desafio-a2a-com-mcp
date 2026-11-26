# Proposal

## Why

O ponto central do desafio é interromper uma reserva sem canal de volta nem estado de continuação no servidor. O MRTR precisa ser seguro desde a primeira versão, pois o token e os argumentos do retry são controlados pelo cliente.

## What Changes

- Completar o caminho de conflito com `input_required`, uma elicitation form e alternativas ordenadas.
- Usar o mecanismo nativo do SDK para proteger e reconstruir `requestState`, com chave estável de `REQUEST_STATE_SECRET` e expiração proposta de 15 minutos.
- Recusar falta de capability, token adulterado ou expirado e argumentos divergentes, antes de qualquer mutação.
- Processar aceitação, `decline` e `cancel`, preservando a semântica de resultado completo.
- Validar a continuação após restart do MCP mantendo o mesmo segredo e identidade do servidor.

## Capabilities

### New Capabilities

- `room-reservation-mrtr`: continuação segura de reservas em conflito, sem sessão ou callback de servidor para cliente.

### Modified Capabilities

Nenhuma. Esta capability acrescenta o caminho de conflito à reserva livre definida em `room-tools`.

## Impact

- Áreas previstas: configuração e tools em `servidor-mcp/`, testes de segurança/HTTP e testes com restart em `tests/`.
- Etapa 3 de 7; aplicar depois de `implement-room-tools`. Próxima: `build-mcp-host`.
- Desenho proposto para revisão: estado com TTL de 900 segundos e rejeição de argumentos divergentes, em vez de aceitar silenciosamente valores adulterados.
- Sem criptografia própria, segredo hardcoded, armazenamento de continuações em memória no MCP ou alterações das pastas imutáveis.
