# Spec Delta

## Purpose

Oferecer consulta e criação determinística de reservas livres, mantendo as regras simples de sala e política exclusivamente no servidor MCP e preservando os dados originais do starter.

## ADDED Requirements

### Requirement: Contratos das três tools
`tools/list` SHALL anunciar `listar_salas`, `consultar_disponibilidade` e `reservar_sala`, cada uma com inputSchema JSON Schema válido de objeto. Consulta SHALL exigir sala, inicio e fim; reserva SHALL exigir também responsavel. Resultados normais das três tools SHALL incluir `structuredContent` e o mesmo JSON em texto.

#### Scenario: Descoberta completa
- **WHEN** o cliente solicita `tools/list`
- **THEN** encontra as três tools e os campos obrigatórios descritos nos respectivos schemas

### Requirement: Reservas locais ao processo
O servidor SHALL carregar as reservas iniciais de `dados/reservas.json` e tornar novas reservas visíveis às operações seguintes do mesmo processo. A execução SHALL preservar os arquivos de `dados/` sem escrita; não SHALL exigir persistência de reservas novas após restart.

#### Scenario: Consulta enxerga reserva recém-criada
- **WHEN** uma reserva livre é criada e a disponibilidade do mesmo intervalo é consultada
- **THEN** a consulta informa o conflito com a nova reserva
- **AND** o arquivo de reservas do starter permanece inalterado

### Requirement: Erros de validação consistentes
Consulta e reserva SHALL aplicar as mesmas validações e devolver `resultType: complete`, `isError: true` e a mensagem exata correspondente no conteúdo. Prefixos acrescentados pelo transporte são permitidos, mas o texto abaixo SHALL permanecer intacto.

| Condição | Mensagem |
|---|---|
| Sala inexistente | `Sala inexistente: <id informado>` |
| Início ou fim fora de 08:00–20:00 em UTC-03:00 | `Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00` |
| Duração maior que duas horas | `Duracao acima do limite: a politica permite no maximo 2 horas` |
| Fim menor ou igual ao início | `Intervalo invalido: fim deve ser posterior a inicio` |

#### Scenario: Sala inexistente
- **WHEN** qualquer uma das duas tools recebe `sala=sala-delorean` com intervalo válido
- **THEN** devolve erro de execução contendo `Sala inexistente: sala-delorean`, sem criar reserva

#### Scenario: Janela violada
- **WHEN** qualquer uma das duas tools recebe uma sala existente para 07:00–08:00 em UTC-03:00
- **THEN** devolve a mensagem exata de janela violada com isError verdadeiro

#### Scenario: Duração excessiva
- **WHEN** qualquer uma das duas tools recebe intervalo 09:00–12:00 em UTC-03:00
- **THEN** devolve a mensagem exata de duração acima do limite

#### Scenario: Intervalo vazio ou invertido
- **WHEN** qualquer uma das duas tools recebe fim anterior ou igual ao início
- **THEN** devolve a mensagem exata de intervalo inválido

### Requirement: Limites temporais da política
As validações SHALL comparar instantes ISO 8601 com offset e aplicar a janela no horário UTC-03:00. Intervalos válidos SHALL permanecer no mesmo dia local, ter início a partir de 08:00, fim até 20:00 e duração de até duas horas. Nenhuma regra SHALL rejeitar uma reserva apenas por estar no passado.

#### Scenario: Limites inclusivos
- **WHEN** uma sala livre é solicitada para 08:00–10:00 ou 18:00–20:00 em UTC-03:00
- **THEN** o intervalo satisfaz a política, inclusive a duração exata de duas horas

#### Scenario: Instantes equivalentes
- **WHEN** o intervalo é informado com outro offset, mas corresponde a 09:00–10:00 em UTC-03:00
- **THEN** a decisão de disponibilidade e política é a mesma do intervalo local equivalente

#### Scenario: Data fixa anterior ao relógio da máquina
- **WHEN** um intervalo válido do starter está no passado em relação ao dia de execução
- **THEN** a política não o rejeita por esse motivo

### Requirement: Consulta de sobreposição
`consultar_disponibilidade` SHALL devolver sala, livre e conflitos, incluindo id, início, fim e responsável das reservas conflitantes. Intervalos SHALL conflitar quando início pedido for anterior ao fim existente e fim pedido posterior ao início existente; encontros apenas nas bordas não SHALL conflitar.

#### Scenario: Conflito com reserva inicial
- **WHEN** o cliente consulta sala-garagem em 03/11/2026 das 14:00 às 15:00 em UTC-03:00
- **THEN** livre é falso e conflitos inclui res-0001

#### Scenario: Intervalos adjacentes
- **WHEN** uma reserva termina exatamente quando outra começa
- **THEN** a consulta não trata o contato de borda como sobreposição

### Requirement: Criação de reserva livre
`reservar_sala` SHALL criar uma única reserva por chamada bem-sucedida em intervalo livre e válido. O resultado SHALL trazer reserva, reservado verdadeiro, sala, inicio, fim, responsavel e politica, com identificador distinto dos já existentes e versão obtida da política. Um conflito não SHALL gerar uma reserva sobreposta nem ser tratado como sucesso; a negociação do conflito é definida em `room-reservation-mrtr`.

#### Scenario: Reserva bem-sucedida
- **WHEN** uma sala existente e livre é solicitada com intervalo válido e responsável Doc
- **THEN** a resposta completa contém a reserva criada, Doc e politica igual a 2026-11-01
- **AND** o JSON em texto equivale ao structuredContent
