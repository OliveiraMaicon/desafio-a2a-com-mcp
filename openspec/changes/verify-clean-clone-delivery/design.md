# Design

## Context

Ver `proposal.md` para o objetivo. Pré-requisito: todas as seis changes de runtime implementadas, terminando em `bridge-task-continuations`. O validador original usa biblioteca padrão, altera reservas ao longo da execução e exige os dois processos recém-iniciados. `validador/README.md` explicita que restart e inspeção de logs ficam fora das 36 verificações.

`specs` está deliberadamente dispensado por `skip_specs: true`: esta etapa verifica contratos existentes e documenta sua execução, sem inventar comportamento novo. O design é necessário porque o harness de verificação cruza processos, reinício, logs e um ambiente limpo.

## Goals / Non-Goals

**Goals:** produzir evidência real e reproduzível da entrega, com distinção entre testes automáticos e inspeções complementares.

**Non-Goals:** alterar validador ou fixtures para passar, acrescentar container/deploy, fabricar saída PASS ou publicar commits sem pedido.

## Decisions

### Testes complementares fora do starter

Consolidar os testes incrementais em `tests/` e, somente se útil, scripts de verificação próprios na raiz. Usar subprocessos com ambiente controlado, espera de prontidão e encerramento apenas dos PIDs criados pelo harness. Não usar encerramento amplo por nome de processo ou por porta.

O cenário de restart mantém token no cliente, segredo e identidade do MCP, reinicia só o servidor MCP e retoma em até 15 minutos. Testes de expiração usam relógio de teste ou mecanismo equivalente já definido na change MRTR, sem reduzir o TTL de produção para um valor fora do contrato.

### Evidência em três níveis

1. Testes próprios de contratos e segurança, inclusive headers divergentes, schemas completos, logs e não vazamento de cada token do agente.
2. Execução intacta de `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301`, com processos novos, saída integral e código 0.
3. Reprodução dos comandos documentados em checkout limpo da implementação, com ambiente virtual novo e sem configurações locais herdadas além do segredo gerado para o teste.

36 PASS não substituem os outros níveis. Também não se deve repetir cenários manuais em um processo já modificado esperando alternativas de um estado inicial; reiniciar quando a inspeção depender dos dados iniciais.

### README é a interface de operação

Substituir o README somente na execução desta change, preservando as quatro seções: Como rodar; Onde a ponte acontece; Decisões técnicas; Saída do validador. Usar caminhos reais da implementação para explicar pausa e retry. Incluir geração/exportação de segredo, manutenção da mesma chave no restart, pré-requisitos reais de Python, instalação reproduzível, dois terminais e reinício antes de validar.

Colar a saída real completa, não um exemplo esperado. Documentar armazenamento em memória, expiração escolhida e limites de restart. Uma limitação real de SDK deve incluir evidência e impacto, nunca ser escondida por um bypass de protocolo.

### Checkout limpo sem publicação implícita

Preferir clone local do fork/checkout que já contenha a implementação quando estiver disponível. Se a implementação ainda não estiver commitada, não criar commit ou push automaticamente para viabilizar o teste: informar a limitação e usar cópia limpa e controlada dos arquivos como ensaio preliminar, deixando a verificação estrita de clone pendente até haver revisão Git autorizada.

Comparar arquivos protegidos com o starter/base de referência e com Git, além de verificar ausência de SDK de LLM e segredos em arquivos da entrega. Repositório público e branch main são itens a conferir no estado disponível, não autorização para mudar branch, criar fork ou fazer push.

## Risks / Trade-offs

- [Validação repetida muda disponibilidade] -> reiniciar ambos os processos e isolar cada cenário que depende do estado inicial.
- [README usa dependências globais sem perceber] -> executar em ambiente virtual e checkout novos.
- [Saída parece válida, mas o processo retornou erro] -> capturar saída integral e código de saída, não só procurar PASS.
- [Log contém trace de chamada direta do validador, não do agente] -> correlacionar trace, ordem tools/list e chamadas originadas do fluxo A2A.
- [Auditoria lê ou publica segredo] -> comparar apenas presença/formato e procurar padrões sem imprimir valores; nunca colar ambiente completo na evidência.

## Migration Plan

Não há mudança de runtime planejada. Acrescentar testes/procedimentos e atualizar documentação com evidência conferida. O harness remove apenas seus recursos temporários e encerra seus próprios processos. Se houver falha funcional, corrigir o subsistema responsável mantendo seus contratos e repetir a verificação do zero. Encerrar com revisão dos artefatos e documentação, sem commit, push, apply adicional ou archive automático.
