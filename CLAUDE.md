# CLAUDE.md — mcp2-na-pratica

Kit aberto (MIT) que ensina as novidades do MCP de 24/11/2026 (Skills over MCP, Tasks, Elicitation; File Uploads só citado) com uma lojinha na Black Friday.

- Repo: `inematds/mcp2-na-pratica`. Autor dos commits: `inematds <inematds@gmail.com>`.
- Python: `.venv` com `mcp==2.3.0` e `pytest`. Testes: `.venv/bin/python -m pytest -q` (todos precisam passar).
- O SDK 2.3.0 não traz as extensões de skills nem de tasks: elas estão em `servidor.py` (`SkillsExtension`, `TasksExtension`) e o lado cliente em `loja_cliente.py`. Elicitation usa o SDK (`Resolve` + `Elicit`).
- Nunca alterar `exemplos/produtos.csv` em execução; o servidor trabalha em `LOJA_TRABALHO` (padrão `trabalho/`, fora do git).
- Só fatos das fontes oficiais listadas no README. Sem citar vídeos ou canais de terceiros.
- Mudou o demo? Regerar `exemplos/saida-demo.txt`, os PNGs (`ferramentas/terminal_png.py`) e a saída colada no README.
- O guia (pasta `guia/`) é feito por outra pessoa.

## Self-learning

Quando eu for corrigido, ou perceber um erro meu: antes de continuar, escrever a lição como uma regra de uma linha no TOPO da seção Lessons abaixo.

## Lessons

- `claude mcp add --scope project` deixa o servidor "Pending approval" até abrir o claude na pasta; para provar conexão sem sessão, usar o escopo local.
- Com protocolo 2026-07-28 a pergunta (elicitation) volta como `input_required` e a tool é chamada de novo: a pergunta precisa sair igual nas duas rodadas e o efeito colateral só pode acontecer no corpo da tool, depois do "sim".
