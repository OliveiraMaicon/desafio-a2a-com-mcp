# Tasks

## 1. Pré-requisito e armazenamento privado

- [x] 1.1 Confirmar expose-a2a-tasks implementada executando seus testes de sucesso, erro e terminalidade; verificar que o adaptador MCP já distingue resultado completo de continuação pendente.
- [x] 1.2 Criar armazenamento privado por taskId separado do store público, com pedido original, pergunta, alternativas, token e trace; testar independência de entradas e documentar que o token é somente guardado/ecoado, nunca interpretado.
- [x] 1.3 Garantir limpeza da entrada apenas em conclusão terminal e substituição por nova pausa da mesma Task; testar que encerrar uma Task não remove a continuação de outra e que o store público não contém o token.

## 2. Pausa e escolha inválida

- [x] 2.1 Traduzir input_required para INPUT_REQUIRED e encerrar SendMessage; testar mensagem exata alternativas: sala-fusca, sala-mirante com dados iniciais, histórico e GetTask, documentando no executor o ponto da ponte.
- [x] 2.2 Preservar a ordem de enum e tratar const como uma alternativa; testar igualdade byte a byte da mensagem sem saudação, prefixo extra ou quebra de linha.
- [x] 2.3 Processar escolha fora das alternativas mantendo Task e continuação; testar repetição da mensagem, ausência de retry e posterior aceitação válida da mesma Task.

## 3. Retomada, recusa e falhas

- [x] 3.1 Retomar escolha válida via host, com WORKING na mesma Task; capturar o request e testar argumentos originais, chave correta, action accept, content.sala, token intacto e id novo, seguido de COMPLETED com artifact correto.
- [x] 3.2 Traduzir escolha=recusar para decline e aguardar complete sem reserva antes de CANCELED; testar chamada MCP efetiva, ausência de nova reserva e recusa de continuação posterior em Task terminal.
- [x] 3.3 Tratar erro de retry como FAILED seguro e nova elicitation como outra pausa da mesma Task; testar token expirado e mudança de disponibilidade sem vazamento nem reserva fictícia, documentando essa tradução junto ao executor.
- [x] 3.4 Proteger retomadas da mesma Task com guard local sem bloquear GetTask durante I/O; testar rejeição ou serialização de duas continuações simultâneas da mesma Task sem dupla conclusão, sem introduzir transação global de salas.

## 4. Gate integrado da ponte

- [x] 4.1 Testar duas Tasks pausadas com responsáveis/horários distintos, retomadas em ordem inversa; verificar ids de reserva distintos, dados e traces corretos e nenhuma troca de token ou chave.
- [x] 4.2 Capturar os tokens de cada Task e varrer respostas SendMessage/GetTask, card, status, histórico, artifacts e erros; verificar ausência real de cada token e de campo público requestState, além de zero invocações do callback automático.
- [x] 4.3 Repetir pedido conflitante sem efetuar escolhas e comparar as mensagens de pausa byte a byte; verificar identidades distintas de Task e documentar que determinismo não adiciona idempotência de reservas.
- [x] 4.4 Executar o validador original completo com os dois processos recém-iniciados e a suíte incremental; verificar 36 PASS e código 0 antes de seguir para a reprodução da entrega.
