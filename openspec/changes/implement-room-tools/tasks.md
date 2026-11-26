# Tasks

## 1. Pré-requisito e estado de reservas

- [x] 1.1 Confirmar que establish-mcp-transport está implementada e não apenas planejada; executar sua suíte e verificar endpoint, descoberta e resource antes de alterar tools.
- [x] 1.2 Carregar cópias de salas e reservas iniciais em memória e gerar ids acima dos existentes; adicionar testes de inicialização, unicidade e ausência de escrita em dados/, documentando que restart perde reservas novas.

## 2. Validações e disponibilidade

- [x] 2.1 Implementar parsing de instantes com offset e validação compartilhada de sala, intervalo, janela UTC-03:00 e duração; adicionar testes parametrizados das quatro mensagens exatas para consulta e reserva, verificando isError em resultado complete.
- [x] 2.2 Cobrir bordas 08:00 e 20:00, duração exata de duas horas, intervalos vazios, offsets equivalentes, virada de dia e data no passado; verificar decisões coerentes e documentar a precedência estável das validações junto ao código.
- [x] 2.3 Implementar consulta de sobreposição semiaberta e registrar consultar_disponibilidade; testar sala livre, res-0001 em conflito e reservas adjacentes, verificando sala, livre e detalhes dos conflitos.

## 3. Reserva livre e contratos de saída

- [x] 3.1 Registrar reservar_sala com schema que exige responsável e implementar inserção somente quando livre; testar id único, dados originais, versão da política e consulta posterior enxergando a reserva criada.
- [x] 3.2 Definir saídas estruturadas e texto JSON equivalente para consulta e reserva, com schema de reserva preparado para recusa futura; validar schemas e equivalência dos dois formatos em testes HTTP.
- [x] 3.3 Isolar cálculo simples de alternativas para uso posterior, sem duplicá-lo no agente; testar filtro por capacidade, salas livres, desempate por id e limite de três, documentando que a emissão de elicitation pertence à próxima change.
- [x] 3.4 Garantir que o caminho de conflito ainda incompleto não cria sobreposição nem responde com reserva fictícia; testar ausência de mutação e manter essa limitação intermediária explícita nas notas da implementação.

## 4. Gate da etapa

- [x] 4.1 Executar testes de domínio, contratos HTTP e regressão do transporte; verificar descoberta com as três tools, mensagens das verificações 9–12 e preservação dos arquivos do starter antes de seguir para MRTR.
