# Design

## Context

Ver `proposal.md` para motivação e `specs/mcp-transport/spec.md` para o contrato. `servidor-mcp/` e `agente/` contêm somente `.gitkeep`; não há dependências, testes ou aplicação para reaproveitar. O validador envia requests modernos diretamente, sem initialize, e espera JSON em vez de fluxo SSE de resultados.

Este é o primeiro passo da sequência:

```text
establish-mcp-transport --> implement-room-tools --> implement-secure-mrtr
    --> build-mcp-host --> expose-a2a-tasks --> bridge-task-continuations
    --> verify-clean-clone-delivery
```

## Goals / Non-Goals

**Goals:** estabelecer um processo HTTP mínimo com o SDK oficial e capturar falhas de compatibilidade antes de implementar o domínio.

**Non-Goals:** exigir as três tools já nesta etapa, criar uma abstração de serviços ou reimplementar JSON-RPC/Streamable HTTP. O validador completo só será gate depois da ponte.

## Decisions

### SDK oficial com protocolo moderno explícito

Usar `mcp` v2 e a API moderna de servidor, com modo stateless e respostas JSON. A documentação atual do SDK descreve `MCPServer`, MRTR e segurança de requestState; a versão instalada deve ser conferida antes de fixar o pin. Não assumir que qualquer pacote v2 ou exemplo FastMCP v1 implementa o wire de 2026-07-28.

Na execução desta change, conferir os símbolos da distribuição escolhida e um request real do starter; fixar versão exata no `pyproject.toml` e lock, incluindo dependências diretas de execução e teste. A alternativa de implementar envelopes manualmente é rejeitada. Se a distribuição não atender ao protocolo obrigatório, registrar a evidência e interromper essa escolha de versão, sem contornar com protocolo próprio.

### Um ambiente Python, dois entrypoints futuros

Propor um `pyproject.toml` na raiz, ambiente virtual e lock para ambos os processos, sem introduzir gerenciador que exija instalação global. Usar entrypoint fino em `servidor-mcp/` e carregar `dados/` a partir do caminho do projeto, não do diretório corrente do terminal. Declarar a versão mínima real de Python compatível com as dependências; o validador continua exigindo apenas Python 3.10+.

A alternativa de dois ambientes independentes aumenta repetição sem benefício para este desafio. Compartilhar o ambiente não permite compartilhar funções de domínio entre processos.

### SDK cuida do protocolo; adaptação HTTP permanece fina

Deixar validação moderna de metadados, envelopes e headers no transporte do SDK quando suportada. Acrescentar somente adaptação pública necessária para o status HTTP exigido e observação de requests. Testes diretos devem comprovar `-32602`/400 e `-32020`; não confiar apenas nos tipos Python.

O registro em stderr extrai método, id e traceparent sem consumir o corpo de modo que impeça sua leitura pelo SDK. Não registrar corpo integral. A listagem de tools continua extensível para a próxima change, sem teste que fixe exatamente uma tool.

### Resource e saída estruturada sem transformar o starter

Ler salas e Markdown em modo somente leitura. Definir modelo de saída que gere JSON Schema de objeto e devolver texto serializado a partir do mesmo valor do structuredContent. Reutilizar o texto integral do resource; a extração de versão no agente fica para `build-mcp-host`.

## Risks / Trade-offs

- [Documentação de main pode diferir de uma distribuição publicada] -> conferir a versão instalada e congelá-la com teste real de wire antes das próximas changes.
- [SDK traduz exceção para HTTP 200 quando o contrato exige 400] -> testar o status e usar extensão pública de transporte, sem reescrever o dispatcher.
- [Middleware de log interfere no corpo] -> teste HTTP verifica que o mesmo request é registrado e processado corretamente.
- [Lock e metadados do projeto divergem] -> validar instalação em ambiente novo, sem dependências globais implícitas.

## Migration Plan

Não há dados ou serviço existente a migrar. Introduzir o processo e seus testes, mantendo o starter intacto. A reversão desta etapa consiste em parar o novo processo; não apagar ou restaurar arquivos do usuário. Antes de aplicar a próxima change, executar os testes desta etapa e conferir descoberta e resource por HTTP. Implementar e revisar as changes em ordem; os pré-requisitos são manuais, não inferidos como satisfeitos só porque todos os planos existem.
