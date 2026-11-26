"""Demo no terminal: as novidades do MCP numa lojinha na Black Friday.

    .venv/bin/python demo.py --auto     # responde sozinho (bom para gravar tela)
    .venv/bin/python demo.py            # você responde as perguntas

Liga o servidor `servidor.py` por stdio e mostra, passo a passo:
1. SKILL   2. TASK   3. PERGUNTA ANTES DE AGIR (elicitation)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
import time
from typing import Any

from mcp import Client
from mcp_types import ElicitResult

from loja_cliente import ClienteTasks, conferir_skill, parametros_servidor, pedir

COR = not os.environ.get("NO_COLOR")
RITMO = 0.0


def _c(codigo: str, texto: str) -> str:
    return f"\033[{codigo}m{texto}\033[0m" if COR else texto


AMARELO = lambda t: _c("1;93", t)  # noqa: E731
VERDE = lambda t: _c("1;92", t)  # noqa: E731
VERMELHO = lambda t: _c("1;91", t)  # noqa: E731
CIANO = lambda t: _c("96", t)  # noqa: E731
CINZA = lambda t: _c("90", t)  # noqa: E731
BRANCO = lambda t: _c("1;97", t)  # noqa: E731


def linha(texto: str = "") -> None:
    print(texto, flush=True)
    if RITMO:
        time.sleep(RITMO)


def titulo_passo(n: int, nome: str, frase: str) -> None:
    linha()
    linha(AMARELO(f"━━ PASSO {n} DE 3 — {nome} " + "━" * max(4, 44 - len(nome))))
    linha(BRANCO(frase))
    linha()


def barra(feito: int, total: int, largura: int = 20) -> str:
    cheio = round(largura * feito / total) if total else 0
    return "█" * cheio + "░" * (largura - cheio)


# --- respostas às perguntas do servidor -------------------------------------


class Respostas:
    """Responde as elicitations: roteiro fixo (--auto) ou digitando (interativo)."""

    def __init__(self, auto: bool) -> None:
        self.auto = auto
        self.roteiro: list[dict[str, Any]] = []

    async def __call__(self, ctx: Any, params: Any) -> ElicitResult:
        linha(f"  {AMARELO('?')} Servidor pergunta: {BRANCO(chr(34) + params.message + chr(34))}")
        campo, esquema = next(iter(params.requested_schema["properties"].items()))
        if self.auto:
            resposta = self.roteiro.pop(0)
            if resposta["action"] != "accept":
                linha(f"  Resposta: {VERMELHO('cancelar')}")
                return ElicitResult(action=resposta["action"])
            valor = resposta["content"][campo]
        else:
            valor = await asyncio.to_thread(self._perguntar, esquema)
        if isinstance(valor, bool):
            linha(f"  Resposta: {VERDE('SIM') if valor else VERMELHO('NÃO')}")
        else:
            linha(f"  Digitado: {CIANO(chr(34) + valor + chr(34))}")
        return ElicitResult(action="accept", content={campo: valor})

    @staticmethod
    def _perguntar(esquema: dict[str, Any]) -> Any:
        if esquema.get("type") == "boolean":
            return input("  Sua resposta [s/n]: ").strip().lower().startswith("s")
        return input("  Digite: ")


# --- os três passos -----------------------------------------------------------


async def passo_skill(client: Client) -> None:
    titulo_passo(1, "SKILL", "O servidor entrega o playbook junto com as tools.")
    linha(CIANO("→ skills/list"))
    lista = await pedir(client, "skills/list")
    entrada = lista["skills"][0]
    nome = entrada["frontmatter"]["name"]
    linha(f"  {len(lista['skills'])} skill no servidor: {BRANCO(nome)}  (no Claude Code: loja:{nome})")
    linha(CINZA(f"  {entrada['frontmatter']['description']}"))
    linha(f"  Manifesto: {len(entrada['resources'])} arquivos com SHA-256")
    linha()
    linha(CIANO(f"→ resources/read {entrada['uri']}") + CINZA("  (só quando precisa)"))
    textos = await conferir_skill(client, entrada)
    regras = [ln for ln in textos[entrada["uri"]].splitlines() if ln[:2] in ("1.", "2.", "3.")]
    for regra in regras:
        linha("  " + regra.split("**")[0] + regra.split("**")[1])
    linha(VERDE("  ✓ Skill carregada e conferida (tamanho + SHA-256 batem)"))


async def passo_task(client: Client, tasks: ClienteTasks) -> None:
    titulo_passo(2, "TASK", "Trabalho longo roda em segundo plano. Ninguém trava.")
    linha(CIANO("→ tools/call atualizar_precos  (20% off em 300 produtos)"))

    def criada(task: dict[str, Any]) -> None:
        linha(f"  Servidor devolveu na hora: task {BRANCO(task['taskId'][:8])} · {AMARELO(task['status'])}")
        linha(CIANO(f"→ tasks/get a cada {task['pollIntervalMs'] / 1000:.1f} s".replace(".", ",")))

    def mudou(task: dict[str, Any]) -> None:
        msg = task.get("statusMessage", "")
        if task["status"] == "working" and "de" in msg:
            feito, total = (int(x) for x in msg.split()[0:3:2])
            linha(f"  {AMARELO('working')}   {AMARELO(barra(feito, total))}  {feito} de {total}")
        elif task["status"] != "working":
            linha(f"  {VERDE(task['status'])} {VERDE(barra(1, 1))}  {msg}")

    tasks.ao_criar, tasks.ao_mudar = criada, mudou
    resultado = await client.call_tool("atualizar_precos", {"desconto_pct": 20})
    resumo = resultado.structured_content or {}
    linha(
        VERDE(f"  ✓ {resumo.get('com_preco_novo')} preços novos no rascunho")
        + f" · {resumo.get('travados_na_margem')} travados na margem de 15%"
    )


async def passo_pergunta(client: Client, respostas: Respostas) -> None:
    titulo_passo(3, "PERGUNTA ANTES DE AGIR", "O servidor pausa e pergunta. Você decide.")
    tentativas = [({"action": "accept", "content": {"publicar": False}}), ({"action": "accept", "content": {"publicar": True}})]
    for i, roteiro in enumerate(tentativas if respostas.auto else [None]):
        if roteiro:
            respostas.roteiro.append(roteiro)
        linha(CIANO("→ tools/call publicar_precos"))
        r = await client.call_tool("publicar_precos", {})
        texto = r.content[0].text
        linha(f"  {VERDE('✓') if 'publicados' in texto else VERMELHO('✗')} {texto}")
        if respostas.auto and i == 0:
            linha()
    linha()
    nomes = [{"action": "accept", "content": {"nome": "Caneca"}}, {"action": "accept", "content": {"nome": "Caneca Azul P"}}]
    for i, roteiro in enumerate(nomes if respostas.auto else [None]):
        if roteiro:
            respostas.roteiro.append(roteiro)
        linha(CIANO("→ tools/call apagar_produto SKU001") + CINZA("  (destrutivo)"))
        r = await client.call_tool("apagar_produto", {"sku": "SKU001"})
        texto = r.content[0].text
        linha(f"  {VERDE('✓') if 'apagado' in texto else VERMELHO('✗')} {texto}")
        if respostas.auto and i == 0:
            linha()


async def principal(auto: bool) -> None:
    linha(AMARELO("MCP FAZ 2 ANOS — NA PRÁTICA"))
    linha(BRANCO("Lojinha na Black Friday · servidor MCP \"loja\" (stdio)"))
    tasks = ClienteTasks()
    respostas = Respostas(auto)
    with tempfile.TemporaryDirectory(prefix="loja-demo-") as trabalho:
        async with Client(parametros_servidor(trabalho), extensions=[tasks], elicitation_callback=respostas) as client:
            exts = ", ".join(e.split("/")[-1] for e in (client.server_capabilities.extensions or {}))
            linha(CINZA(f"Conectado · protocolo {client.protocol_version} · extensões: {exts}"))
            await passo_skill(client)
            await passo_task(client, tasks)
            await passo_pergunta(client, respostas)
    linha()
    linha(AMARELO("FIM") + " · Skills, Tasks e Elicitation num servidor só. Código aberto (MIT).")


def main() -> None:
    global RITMO
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--auto", action="store_true", help="responde as perguntas sozinho (para gravar tela)")
    ap.add_argument("--ritmo", type=float, default=None, help="pausa entre linhas em segundos (padrão: 0,25 no --auto)")
    args = ap.parse_args()
    RITMO = args.ritmo if args.ritmo is not None else (0.25 if args.auto else 0.0)
    try:
        asyncio.run(principal(args.auto))
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
