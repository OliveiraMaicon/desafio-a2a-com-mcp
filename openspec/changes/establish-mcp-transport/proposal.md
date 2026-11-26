# Proposal

## Why

O starter não contém aplicação, e toda a ponte depende de um servidor MCP compatível com a revisão `2026-07-28`. Esta primeira entrega estabelece uma fronteira HTTP verificável antes de acrescentar regras de reserva e MRTR.

## What Changes

- Preparar ambiente Python reproduzível, com SDK oficial `mcp` v2 e versões exatas no `pyproject.toml`.
- Expor Streamable HTTP em `http://localhost:7301/mcp`, sem negociação de sessão entre requests.
- Implementar `listar_salas` com schemas, conteúdo estruturado e texto JSON equivalente.
- Expor `politica://uso` como resource Markdown e declarar as capabilities de tools e resources.
- Validar metadados obrigatórios e headers espelhados; registrar método, id e traceparent em stderr, inclusive nas rejeições.
- Adicionar testes HTTP próprios fora das pastas imutáveis do starter.

## Capabilities

### New Capabilities

- `mcp-transport`: transporte MCP stateless, descoberta inicial, listagem de salas, resource e observabilidade de requests.

### Modified Capabilities

Nenhuma. O inventário de specs está vazio.

## Impact

- Áreas previstas: `servidor-mcp/`, `pyproject.toml`, arquivo de lock e `tests/` na raiz.
- Fontes de contrato: `README.md`, `contexto.md`, `exemplos/wire/01-tools-list.json` e `05-resources-read-politica.json`.
- Etapa 1 de 7; sem pré-requisito de implementação. Próxima: `implement-room-tools`.
- A descoberta contém apenas `listar_salas` nesta etapa intermediária; a próxima change completa as três tools. Ainda não se espera passar o validador inteiro.
- Não alterar `dados/`, `exemplos/` ou `validador/`; não implementar agente, MRTR, banco, deploy ou interface gráfica.
