# Tasks

## 1. Pré-requisito e configuração segura

- [x] 1.1 Confirmar implement-room-tools implementada executando a suíte existente; conferir que a versão travada do SDK oferece configuração pública de segurança, TTL e vínculo do request, registrando os símbolos realmente utilizados.
- [x] 1.2 Ler REQUEST_STATE_SECRET como chave hexadecimal externa, validar formato e pelo menos 32 bytes decodificados e configurar o mecanismo nativo com identidade estável do servidor; testar falha de startup para segredo ausente, inválido ou curto sem imprimir seu valor e documentar geração/exportação segura junto à configuração.
- [x] 1.3 Configurar validade de 900 segundos e verificação antes de efeitos colaterais; adicionar teste de expiração com relógio controlado e rejeição `-32602`, sem reduzir o TTL de produção para facilitar o teste.

## 2. Emissão da pergunta

- [x] 2.1 Conectar conflito ao InputRequiredResult explícito protegido pelo RequestStateBoundary nativo e ao cálculo de alternativas; testar uma entrada elicitation/create, mode form, schema plano, campo obrigatório sala, ordem sala-fusca/sala-mirante e ausência de mutação antes do retry.
- [x] 2.2 Cobrir alternativa única com enum ou const e ausência de alternativas; verificar corte de três e resultado complete com a mensagem exata Sem alternativas disponiveis no intervalo quando não houver opção.
- [x] 2.3 Exigir elicitation.form no request atual antes de emitir pergunta; testar capabilities vazias, elicitation sem form e declaração form vazia válida, conferindo `-32021`, requiredCapabilities e HTTP 400 somente quando faltar a capability.
- [x] 2.4 Documentar no módulo o ponto que retorna a pergunta em vez de iniciar back-channel; verificar por teste que a resposta HTTP termina sem interação síncrona com o cliente.

## 3. Retomada e segurança de entrada

- [x] 3.1 Processar inputResponses e requestState em params usando a chave original; testar aceitação com novo id e resultado complete contendo a sala escolhida e os demais argumentos originais.
- [x] 3.2 Rejeitar token adulterado, expirado, chave de pergunta incorreta e operação incompatível sem escrita; adicionar testes HTTP verificando erro controlado, `-32602` para falha de estado e ausência de reserva ou erro interno.
- [x] 3.3 Rejeitar argumentos reenviados divergentes antes de executar a tool; testar alteração de sala original, horários e responsável com `-32602`, inclusive consulta posterior confirmando que os valores adulterados não foram usados.
- [x] 3.4 Validar escolha contra alternativas protegidas e conferir disponibilidade novamente; testar escolha externa ao schema e alternativa ocupada entre pausa e retry, sem sobreposição e com nova pausa válida ou erro de ausência de alternativas.
- [x] 3.5 Implementar decline e cancel como conclusão sem reserva; testar complete, isError ausente/falso, reservado falso, motivo presente e ausência de mutação, documentando a distinção entre recusa e erro.

## 4. Gate entre processos

- [x] 4.1 Criar teste que obtém token, reinicia apenas o MCP com a mesma chave e identidade e retoma em um novo processo; verificar reserva concluída sem recuperar mapa de continuações do processo anterior.
- [x] 4.2 Executar as verificações MCP 1–20 do validador original por um harness próprio, sem alterar o arquivo nem exigir A2A ainda, e executar os testes complementares de expiração/restart; conferir logs de ids distintos e que nenhum segredo ou token foi despejado em stderr.
