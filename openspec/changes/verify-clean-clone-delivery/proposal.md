# Proposal

## Why

As 36 verificações não cobrem sozinhas todos os requisitos: restart, logs e reprodução em clone limpo exigem evidência complementar. A entrega precisa poder ser executada apenas pelo README, sem conhecimento da sessão de desenvolvimento.

## What Changes

- Consolidar testes complementares e procedimentos de verificação sem alterar o validador original.
- Executar o validador com os dois processos recém-iniciados e registrar a saída integral real.
- Verificar logs, retry com id novo, restart do MCP, expiração, integridade e ausência de vazamento.
- Substituir o README pelas quatro seções exigidas e comandos conferidos em checkout limpo da implementação.
- Auditar preservação de `dados/`, `exemplos/` e `validador/`, dependências determinísticas e ausência de segredos.

## Capabilities

### New Capabilities

Nenhuma. Esta change só consolida testes, procedimentos e documentação; não acrescenta comportamento de runtime.

### Modified Capabilities

Nenhuma. `skip_specs: true` dispensa deliberadamente deltas de spec, sem requisitos artificiais de produto.

## Impact

- Áreas previstas: `README.md`, testes e eventuais scripts de verificação próprios fora das pastas imutáveis.
- Etapa 7 de 7; aplicar depois de `bridge-task-continuations`, com todas as anteriores implementadas.
- Correções que mudem os contratos de runtime devem ser reconciliadas com a change responsável; este planejamento não autoriza reduzir o contrato para fazer o teste passar.
- Não executar commit, push, publicação ou archive automaticamente. Entregar na `main` do fork público continua sendo requisito do desafio, mas operações Git de publicação exigem pedido do usuário.
