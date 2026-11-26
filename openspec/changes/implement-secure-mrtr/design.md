# Design

## Context

Ver `proposal.md` e `specs/room-reservation-mrtr/spec.md`. Pré-requisito: `implement-room-tools` implementada. A documentação Python atual descreve `RequestStateSecurity(keys=[...])` e avisa que a chave padrão é efêmera; a mesma identidade de servidor também deve ser preservada, pois participa do vínculo do token.

## Goals / Non-Goals

**Goals:** obter MRTR nativo com verificação antes de efeitos colaterais e reconstrução independente do processo anterior.

**Non-Goals:** desenhar formato próprio de token, autenticação, distribuição multiworker, persistência de reservas ou garantia adicional de idempotência/replay global após restart.

## Decisions

### MRTR nativo, não pergunta síncrona

Retornar `InputRequiredResult` explicitamente na camada de tratamento MCP, sem chamada de elicitation por back-channel. O `RequestStateBoundary` nativo do SDK envolve essa camada: sela a resposta e verifica o retry antes de qualquer efeito colateral. A integração preserva o catálogo e os resultados completos existentes. O conflito calcula alternativas, produz um único schema plano e termina a chamada HTTP. A chave da pergunta pertence ao servidor, não a uma constante esperada pelo cliente; ela e as alternativas são incluídas no estado selado e validadas no retry.

O token deve proteger argumentos originais, contexto da pergunta, alternativas e vínculos da operação necessários à continuação. Confirmar esses vínculos na versão fixada, usando testes de argumentos e tool incompatível; tipos ou documentação de outra versão não são evidência suficiente. O retorno explícito evita o resolver automático, que nesta versão não oferece a integração necessária para o conflito dinâmico.

### Segredo estável, sem implementação criptográfica própria

Proposta de configuração: `REQUEST_STATE_SECRET` contém 64 caracteres hexadecimais gerados por `secrets.token_hex(32)`. Decodificar para 32 bytes e recusar formato inválido ou tamanho insuficiente. Passar os bytes ao mecanismo nativo `RequestStateSecurity`, mantendo nome/identidade estável do servidor entre reinícios. Não emitir token com a chave aleatória padrão do processo.

HMAC/AEAD manual é alternativa rejeitada: o SDK já oferece proteção, verificação e vínculo ao request. Confidencialidade do token não é requisito; opacidade para o agente continua obrigatória mesmo que o payload seja legível. Não registrar o segredo nem o token.

### TTL e divergência como escolhas propostas

Adotar 900 segundos como default de desenho, dentro do intervalo obrigatório de 5–30 minutos. Usar configuração de TTL do SDK; testar expiração com relógio controlado pelo teste ou mecanismo equivalente que não enfraqueça a produção.

Entre os dois comportamentos aceitos pelo desafio, escolher rejeitar argumentos divergentes com `-32602` antes da tool. Isso simplifica auditoria e evita sucesso aparente quando o cliente enviou dados diferentes. A aprovação deste plano não significa que o usuário tenha escolhido pessoalmente esses detalhes; são defaults explícitos para revisão.

### Resposta válida não congela disponibilidade

O token sela a pergunta e o pedido, não uma reserva de sala. Ao aceitar, validar a resposta contra o schema protegido e conferir novamente a disponibilidade antes da escrita. Se a alternativa ficou ocupada, recalcular alternativas para a capacidade do pedido original e devolver nova pausa, ou o erro de ausência de alternativas. Isso evita sobreposição sem introduzir locks distribuídos.

Decline/cancel concluem com reservado falso e motivo, sem isError. A verificação de capability form ocorre somente se houver uma pergunta a emitir; no conflito sem alternativas prevalece o erro de execução previsto.

## Risks / Trade-offs

- [Segredo gerado novamente durante restart] -> teste reinicia só o MCP com o mesmo ambiente e nome, preservando o token do cliente.
- [Biblioteca armazena informação indispensável somente em memória] -> teste entre processos prova reconstrução; se falhar por limitação real, registrar evidência, sem adicionar mapa de sessões como contorno.
- [Tamper causa erro interno ou mutação] -> variar caracteres e estrutura do token, conferir `-32602` e consultar ausência de reserva.
- [Alternativas mudam enquanto o usuário decide] -> revalidar e permitir outra pausa; a ponte posterior precisa suportar esse retorno.
- [Sem autenticação, token não identifica usuário autorizado] -> manter isso fora de escopo; integridade não é autenticação.

## Migration Plan

Introduzir a configuração obrigatória de segredo antes de habilitar MRTR. Reiniciar com a mesma configuração mantém tokens ainda válidos; mudar chave ou identidade invalida tokens e exige iniciar novo fluxo. Não há migração de reservas. Executar os testes MCP 1–20 em processos novos, além dos testes de expiração e restart que o validador não realiza. Não iniciar o agente nesta change.

## References

- SDK Python: `https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/handlers/multi-round-trip.md` (referência de descoberta; conferir contra a versão travada).
- Contratos locais: exemplos wire 03, 04, 06 e 11; verificações 13–20 de `validador/validar.py`.
