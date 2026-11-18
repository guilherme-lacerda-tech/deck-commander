# Auditoria técnica — 18/11/2026

## Resultado atual

O código passou em **986 testes automatizados** (3 ignorados por dependerem do ambiente) em 50,64 s, executados com
`PYTHONPATH=. python -m pytest -q`. A validação de sintaxe de `dc/` e `decky-plugin/` também passou.

Não foi assumido como evidência nenhum teste ou relato de outra conversa. Os resultados abaixo foram executados nesta
revisão ou são cenários cobertos explicitamente pela suíte do repositório.

## Correções verificadas nesta revisão

1. **Travamento durante a partida:** o monitor lê o CSV crescente do MangoHud, espera pelo menos 20 amostras e 15 s,
   alerta apenas quando a queda é sustentada e prepara uma resolução menor para a próxima abertura. Ele não modifica
   um PCSX2 já aberto, pois o emulador só aplica a configuração com segurança ao iniciar.
2. **Queda de 60%–70%:** foi acrescentado o cenário 60 FPS estáveis -> 42 FPS. O monitor preserva a meta estável já
   observada (60) em vez de reinterpretar a janela lenta como uma meta de 50 FPS. Assim, 42 FPS agora gera o alerta e
   a preparação para a próxima partida.
3. **CSV em criação:** o intervalo em que o MangoHud já criou o arquivo, mas ainda não escreveu o cabeçalho, não
   derruba o monitor; ele simplesmente tenta de novo.
4. **Atualização segura:** o pacote baixado agora verifica que cada item está realmente dentro do diretório temporário,
   inclusive para nomes que apenas parecem compartilhar o mesmo prefixo. Os caminhos do script de troca também são
   citados corretamente para não virarem interpretação de shell se tiverem caracteres especiais.

## Matriz de instalação coberta

Os testes de plugin e configuração cobrem instalação sem plugin, instalação parcial, plugin já correto, manifesto
malformado, falta de permissão, configuração de emulador ausente, JSON inválido, formato inválido, emulador ausente e
emulador válido já escolhido pelo usuário. A reparação copia todos os arquivos do plugin, inclusive subdiretórios.

## Segurança e manutenção

- Não há `shell=True`, `os.system`, `eval` ou `exec` no caminho auditado de instalação, lançamento e painel.
- O backend do plugin chama o painel com `asyncio.create_subprocess_exec`; a ação é limitada a caracteres seguros e o
  painel mantém uma lista explícita de ações válidas.
- O linter encontrou 270 avisos já existentes, principalmente estilo, anotações de classe e tratamento explícito de
  retorno de subprocessos. Eles não falharam os testes. Não foram corrigidos em massa para não misturar uma refatoração
  extensa e arriscada com esta entrega funcional.

## Limites que ainda exigem aparelho real

Não é correto declarar validação total sem estes itens:

1. Abrir o Devil May Cry 3 no PCSX2 do Steam Deck, reproduzir uma queda sustentada e confirmar o aviso no painel/bot;
2. Fechar e abrir o jogo para confirmar a resolução segura preparada pelo alerta;
3. Validar a Steam autenticada e o fluxo gráfico completo no Deck físico. A VM disponível nesta revisão não expõe uma
   GPU Vulkan funcional para o cliente Steam, portanto ela não substitui esse teste.

Esses limites são de ambiente e credenciais, não falhas que os testes automatizados tenham conseguido reproduzir.
