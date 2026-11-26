# Design

## Context

Ver `proposal.md` e `specs/room-tools/spec.md`. Pré-requisito: `establish-mcp-transport` implementada e seus testes passando. Os JSONs entregam cinco salas e duas reservas; a política fixa janela e duração. Não existe necessidade de modelo persistente ou camada de serviços.

## Goals / Non-Goals

**Goals:** manter uma única implementação pequena das validações e da sobreposição, compartilhada pelas duas tools no processo MCP.

**Non-Goals:** negociação MRTR nesta etapa, idempotência de reserva, persistência em disco ou controle transacional de escrita concorrente.

## Decisions

### Estado em memória inicializado pelo starter

Manter uma cópia local das reservas e índice simples de salas em um módulo pequeno de `servidor-mcp/` (por exemplo, `salas.py`). Obter novos ids por sequência acima dos ids carregados. Isso permite consultar imediatamente uma reserva criada e produzir resultados previsíveis sem gravar `dados/reservas.json`.

Banco, ORM e persistência em arquivo são alternativas rejeitadas por custo e por desviarem do foco do desafio. Cada novo processo recarrega o estado inicial.

### Datas como instantes, política como horário local fixo

Usar datetime com offset, comparar instantes e normalizar para UTC-03:00 para validar a janela. Usar intervalos semiabertos `[inicio, fim)` para sobreposição. A normalização serve para decisão; preservar no resultado os valores contratuais do pedido quando não houver necessidade de conversão.

Ordenar validações para impedir mensagens enganosas: sala existente, intervalo estritamente crescente, janela local e duração máxima. Para entradas que violem múltiplas regras, manter essa precedência estável. Datas malformadas ou sem offset são rejeitadas de forma controlada, sem traceback público; o contrato não fixa uma mensagem adicional para esses casos.

Comparar strings de horário ou usar o fuso da máquina são alternativas rejeitadas: offsets equivalentes poderiam produzir decisões diferentes.

### Ferramentas finas com saída única

Usar funções pequenas para validar, localizar sobreposições e inserir reserva. Ambas as tools chamam as mesmas validações. O adaptador MCP converte falhas de negócio para resultado completo com isError, preservando as mensagens especificadas; não tratá-las como exceção JSON-RPC de protocolo.

Derivar JSON em texto e structuredContent do mesmo valor. Definir schemas para disponibilidade e reserva; a forma de reserva deve acomodar no futuro `reservado: false` e motivo, sem tornar obrigatório um id no caminho de recusa.

### Contrato incremental do caminho de conflito

Nesta etapa, testar consultas de conflito e criação apenas em sala livre. Preparar função de alternativas sem colocá-la no agente. Não publicar um falso contrato final para conflito: sua negociação será implementada na próxima change. Um conflito nunca pode escrever sobreposição; enquanto MRTR não existir, tratá-lo como caminho intermediário não concluído, sem afirmar conformidade completa.

## Risks / Trade-offs

- [Estado dos testes contamina a próxima execução] -> criar armazenamento novo por teste e processos novos por suíte de integração.
- [Datas com offsets ou bordas geram falsos conflitos] -> casos de equivalência de instantes, intervalos adjacentes, 08:00, 20:00 e duas horas exatas.
- [Prefixos de erro mudam entre SDKs] -> testar presença da mensagem exata no conteúdo e isError, não depender de prefixo específico.
- [Reserva recebe politica hardcoded] -> extrair a versão do Markdown carregado pelo próprio servidor; o agente fará leitura independente via resource.

## Migration Plan

Acrescentar as duas tools ao processo existente e executar regressão do transporte. Nenhum arquivo de dados é migrado. Reiniciar o processo restaura somente as reservas iniciais e perde deliberadamente as reservas de execução. A próxima etapa é `implement-secure-mrtr`; só ela torna o caminho de conflito completo.
