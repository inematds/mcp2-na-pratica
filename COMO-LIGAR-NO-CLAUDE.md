# Como ligar a loja no Claude Code

Precisa do Claude Code **v2.1.331 ou mais novo** (Skills over MCP está em beta pública). Confira com `claude --version`.

## 1. Adicionar o servidor

Dentro da pasta do kit (já com o `.venv` criado):

```bash
claude mcp add loja -- "$PWD/.venv/bin/python" "$PWD/servidor.py"
```

Use sempre o caminho completo (`$PWD/...`) para o Python do `.venv` e para o `servidor.py`.

Conferir:

```bash
claude mcp list
# loja: <kit>/.venv/bin/python <kit>/servidor.py - ✔ Connected
```

**Atenção ao escopo.** Com `--scope project`, o servidor vai para o `.mcp.json` da pasta e aparece como `⏸ Pending approval` até você abrir o `claude` ali e aprovar. O escopo padrão (`local`) conecta direto.

## 2. Ver dentro do Claude Code

Abra `claude` e digite:

- `/mcp` → `loja` mostra `✔ connected`, `Protocol: 2026-07-28` e `3 tools · 2 resources · 1 skill`.
- `/skills` → aparece **`loja:promocao`** com a origem `mcp`. O nome é sempre `<servidor>:<skill>`.

A skill só entra no contexto quando o Claude precisa dela (o `/skills` mostra cerca de 30 tokens para ela).

## 3. Usar

Peça, por exemplo: *"monte uma promoção de 20% na loja e me pergunte antes de publicar"*. O Claude pode carregar `loja:promocao`, chamar `atualizar_precos` e depois `publicar_precos`, que pergunta a você antes de publicar.

## Limites

- **Não funciona em `claude -p`** (modo sem tela): Skills over MCP é só na sessão interativa.
- Nosso teste no Claude Code 2.1.332 ([prova](exemplos/prova-claude-code.txt)) confirmou a conexão, o protocolo 2026-07-28 e a skill `loja:promocao` em `/skills`. **Não** pedimos ao modelo para rodar as tools ali, então não mostramos tasks nem perguntas (elicitation) dentro do Claude Code. As duas estão provadas pelo `demo.py` e pelos testes. Se o cliente não declarar a extensão de tasks, `atualizar_precos` responde do jeito antigo (espera e devolve o resultado).

## Tirar

```bash
claude mcp remove loja
```

Documentação oficial: <https://code.claude.com/docs/en/mcp>
