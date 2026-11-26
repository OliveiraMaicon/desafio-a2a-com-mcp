# Design

## Context

Ver `proposal.md` e `specs/task-continuation-bridge/spec.md`. Pré-requisito: `expose-a2a-tasks` implementada; o host manual já retorna continuação e sabe retomá-la. Esta change preenche o branch de conflito do executor, sem acrescentar regra de sala ao agente.

## Goals / Non-Goals

**Goals:** tornar pausa e retomada explícitas, auditáveis e isoladas por Task, mantendo o token fora da fronteira A2A.

**Non-Goals:** persistir Tasks em disco, autenticar usuários, criar uma fila distribuída ou deduplicar reservas por texto do pedido.

## Decisions

### Duas representações ligadas somente por taskId

Manter Task pública no store do SDK e continuação privada em um mapa separado, por exemplo em `agente/continuations.py`. Cada entrada contém cópia do pedido original, chave da pergunta, alternativas normalizadas de enum/const, token opaco e traceparent da Task. Não adicionar a entrada a metadata, histórico, exception repr ou artifact.

```text
taskId --> Task publica: estado, historico, artifact
       --> Continuacao privada: pedido, pergunta, token, trace
```

Usar somente uma estrutura global de último token é alternativa rejeitada: os testes intercalam duas Tasks. Anexar o token ao objeto público também é rejeitado pelo risco de serialização implícita.

### Máquina de estados como tradução, não orquestração inteligente

```text
SUBMITTED --> WORKING --> COMPLETED
                 |
                 +--> FAILED
                 |
                 +--> INPUT_REQUIRED -- escolha valida --> WORKING
                             |
                             +-- escolha invalida --> INPUT_REQUIRED

WORKING -- decline confirmado pelo MCP --> CANCELED
```

Gerar a mensagem de alternativas por concatenação determinística dos ids na ordem recebida. Escolha inválida só repete a pausa e não chama MCP. Recusa válida é encaminhada como decline; só depois do complete com reservado falso a Task vira CANCELED. O método CancelTask externo não faz parte do escopo.

### Continuação como novo request, mesma Task

Para uma escolha válida, carregar a entrada pelo taskId, transitar para WORKING e invocar o método de retomada do host. Não abrir nova Task nem substituir argumentos originais pela sala escolhida. O host inclui content.sala na resposta à elicitation e obtém novo id MCP; os ids dos envelopes A2A não controlam esse id.

Após sucesso, recusa ou falha terminal, remover a continuação privada daquela Task. Se o MCP pedir outra escolha, substituir somente sua entrada, mantendo o contexto da Task. Token expirado produz falha segura, não geração local de token novo nem retry silencioso sem estado.

### Isolamento de operações e contexto

Usar contexto por Task para trace. Se uma continuação não trouxer traceparent, preservar o contexto guardado; não deixar um header de outra Task alterar a operação. Serializar retomadas da mesma Task com mecanismo local curto ou guard de estado para evitar dupla conclusão, sem segurar lock de GetTask durante I/O. Não introduzir controle transacional global de reservas, explicitamente fora de escopo.

### Testes inspecionam ausência real de vazamento

O validador procura um prefixo de um token obtido por outro caminho; isso não prova ausência de qualquer token do agente. Os testes próprios devem capturar cada token entregue ao host e varrer card, SendMessage, GetTask, histórico, artifacts e erros, inclusive após falha de retry. Devem também conferir que o guard de elicitation automática não foi invocado.

## Risks / Trade-offs

- [Concluir uma Task apaga a continuação de outra] -> teste com duas pausas, responsáveis e horários distintos, retomadas em ordem inversa.
- [Erro do SDK incorpora token no texto] -> sanitizar falhas de protocolo antes de construir mensagens públicas, mantendo o erro de negócio exato quando não contém dados privados.
- [Alternativa ficou ocupada ou token expirou] -> aceitar nova pausa ou falha do MCP sem recalcular domínio no agente.
- [Restart do agente perde a Task] -> limitação intencional documentada; não confundir com restart do MCP, que precisa funcionar com token válido.
- [Ids e timestamps tornam a pergunta não determinística] -> comparar apenas o texto exato exigido, sem prefixos ou dados variáveis.

## Migration Plan

Adicionar o armazenamento privado e conectar o branch pendente ao executor. Testar caminho feliz e falha anteriores como regressão. Depois, executar todos os cenários de pausa, escolha inválida, aceitação, recusa e interleaving. A etapa seguinte consolida o validador e a reprodução em clone limpo; não publicar nem arquivar automaticamente.
