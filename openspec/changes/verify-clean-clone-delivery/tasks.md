# Tasks

## 1. Pré-requisitos e harness de verificação

- [x] 1.1 Confirmar as seis changes anteriores implementadas e executar sua suíte completa; verificar que a sequência de planos não foi confundida com autorização ou conclusão de implementação.
- [x] 1.2 Consolidar fixtures/harness em testes próprios fora de dados/, exemplos/ e validador/, com processos isolados, espera de prontidão e encerramento só dos PIDs criados; testar duas execuções consecutivas independentes e documentar o procedimento junto ao harness.
- [x] 1.3 Auditar preservação das pastas imutáveis contra Git e starter/base de referência, pins/lock e ausência de SDK de LLM ou segredo hardcoded; produzir resultado verificável sem imprimir valores de segredo.

## 2. Evidências complementares de protocolo

- [x] 2.1 Executar restart apenas do MCP entre input_required e retry, mantendo segredo e identidade; verificar conclusão em processo novo e documentar comandos e limitação de perda de reservas novas.
- [x] 2.2 Executar testes próprios de token adulterado/expirado, argumentos divergentes, capabilities incompletas e headers espelhados divergentes; verificar rejeições e ausência de mutação sem alterar o TTL de produção.
- [x] 2.3 Correlacionar logs do fluxo A2A com tools/list anterior ao primeiro tools/call, trace-id do cliente e ids diferentes entre chamada inicial e retry; registrar evidência sem token, segredo ou corpo integral.
- [x] 2.4 Reexecutar isolamento de duas Tasks, escolha inválida, recusa, estado terminal e varredura de todos os tokens capturados; verificar resultados e documentar quais garantias excedem a cobertura do validador original.

## 3. README executável

- [x] 3.1 Substituir README com Como rodar, Onde a ponte acontece, Decisões técnicas e Saída do validador; conferir títulos e incluir versão real de Python, instalação a partir do lock, geração/exportação de segredo, dois terminais, comandos de validação e requisito de processos novos.
- [x] 3.2 Apontar caminhos/funções reais da pausa e retomada e explicar memória, TTL, vínculo da chave no restart e opacidade do token; verificar a explicação contra a implementação e, se houver limitação real de SDK, incluir evidência concreta sem esconder incompatibilidade.
- [x] 3.3 Rodar `python3 validador/validar.py --agente http://localhost:7300 --mcp http://localhost:7301` com ambos os processos novos e colar a saída integral real no README; verificar 36 PASS, zero FAIL e código de saída 0, sem fabricar ou resumir a saída exigida.

## 4. Gate de clone limpo e entrega

- [x] 4.1 Reproduzir somente os comandos do README em clone limpo da implementação com ambiente virtual novo; verificar instalação, card, ambos os processos e validador. Se os arquivos ainda não estiverem commitados, registrar esse bloqueio e fazer apenas ensaio preliminar em cópia controlada, sem marcar a verificação estrita como concluída nem criar commit/push automaticamente.
- [x] 4.2 Repetir as inspeções manuais do avaliador com processos restaurados ao estado inicial quando necessário; verificar alternativas corretas, aceitação, recusa, sala inexistente, tamper, restart e falta de capability.
- [x] 4.3 Revisar README, saída real e auditoria final de arquivos protegidos/segredos; verificar o estado disponível de fork público e branch main, listar qualquer pendência de publicação e encerrar sem commit, push ou archive não solicitado.
