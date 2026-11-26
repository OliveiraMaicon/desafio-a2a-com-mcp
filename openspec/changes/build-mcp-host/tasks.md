# Tasks

## 1. Pré-requisito e cliente moderno

- [x] 1.1 Confirmar implement-secure-mrtr implementada executando os testes MCP diretos e de restart; verificar a API manual e a declaração de capabilities na versão Python exata já travada.
- [x] 1.2 Criar adaptador em agente/ usando cliente oficial por HTTP, com ciclo de vida e encerramento explícitos; testar conexão ao MCP separado e ausência de imports de domínio de servidor-mcp/.
- [x] 1.3 Configurar elicitation.form pela API pública, usando callback guard somente se necessário para anunciar capability; testar que a capability chega ao servidor e o guard nunca é invocado ao receber input_required em modo manual.

## 2. Descoberta, política e contexto

- [x] 2.1 Descobrir tools antes do primeiro tools/call e conferir a tool necessária contra o catálogo recebido; testar ordem no log e falha clara se a tool não existir, sem fallback para schemas hardcoded.
- [x] 2.2 Ler politica://uso e extrair a versão da primeira linha; testar leitura real por HTTP e falha controlada para formato inválido em fixture própria, sem ler diretamente dados/ no agente.
- [x] 2.3 Garantir metadados e headers espelhados em descoberta, resource, tool e retry; capturar requests em testes e verificar versão, elicitation.form, método e nome em todas as pernas.
- [x] 2.4 Passar traceparent por contexto explícito e preservá-lo na continuação; testar operações intercaladas com traces distintos e retomada sem novo header, documentando a diferença entre cache de aplicação e sessão de protocolo.

## 3. API manual de início e retomada

- [x] 3.1 Expor início que devolve resultado completo ou continuação privada; testar retorno imediato de input_required e ausência de segundo tools/call sem resposta explícita da aplicação.
- [x] 3.2 Expor retomada que preserva nome, cópia dos argumentos, chave e token e usa id novo; testar accept, decline e comparação byte a byte do token reenviado, sem decodificá-lo.
- [x] 3.3 Normalizar alternativas recebidas em enum/const e preservar categorias de erro; testar alternativa única e texto exato de Sala inexistente sem implementar cálculo de salas no host.
- [x] 3.4 Documentar a API interna de resultado completo/pendente em docstrings e disponibilizar exercício de teste ou script manual fora do starter; verificar o ciclo completo de MRTR sem A2A e sem atendimento automático do callback.

## 4. Gate da etapa

- [x] 4.1 Executar integração do host contra MCP separado nos caminhos livre, conflito/aceitação, recusa e erro; conferir descoberta anterior à tool, ids distintos e ausência de mutação até escolha explícita antes de adicionar A2A.
