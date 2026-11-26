"""Servidor MCP "loja" — lojinha brasileira na Black Friday.

Mostra três novidades do MCP (24/11/2026) num servidor stdio só:

1. Skills over MCP  -> extensão `io.modelcontextprotocol/skills` (skill `promocao`)
2. Tasks            -> extensão `io.modelcontextprotocol/tasks` (tool `atualizar_precos`)
3. Elicitation      -> perguntas ao usuário (tools `publicar_precos` e `apagar_produto`)

O SDK Python `mcp` 2.3.0 já traz elicitation pronta (`Resolve` + `Elicit`) e o
encanamento genérico de extensões (`Extension`, `MethodBinding`,
`intercept_tool_call`), mas NÃO traz as extensões de skills nem de tasks.
Por isso as duas estão escritas aqui, no mínimo que a especificação pede.

Nada é impresso no stdout (é o canal do protocolo). Os arquivos de trabalho
ficam em `LOJA_TRABALHO` (padrão: ./trabalho), nunca no CSV de exemplo.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Annotated, Any

from mcp.server.extension import Extension, MethodBinding, ResourceBinding
from mcp.server.mcpserver import (
    AcceptedElicitation,
    Elicit,
    ElicitationResult,
    MCPServer,
    Resolve,
)
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.resources import TextResource
from mcp_types import RequestParams
from pydantic import BaseModel, Field

KIT = Path(__file__).resolve().parent
PASTA_SKILLS = KIT / "skills"
CSV_EXEMPLO = KIT / "exemplos" / "produtos.csv"

SKILLS_ID = "io.modelcontextprotocol/skills"
TASKS_ID = "io.modelcontextprotocol/tasks"
CLIENT_CAPS_META = "io.modelcontextprotocol/clientCapabilities"

MARGEM_MINIMA_PCT = 15


# ---------------------------------------------------------------------------
# Loja: catálogo, regras da skill e arquivos de trabalho
# ---------------------------------------------------------------------------


def pasta_trabalho() -> Path:
    pasta = Path(os.environ.get("LOJA_TRABALHO", KIT / "trabalho"))
    pasta.mkdir(parents=True, exist_ok=True)
    catalogo = pasta / "catalogo.csv"
    if not catalogo.exists():
        shutil.copyfile(CSV_EXEMPLO, catalogo)
    return pasta


def centavos(valor: str) -> int:
    reais, _, cent = valor.partition(".")
    return int(reais) * 100 + int((cent + "00")[:2])


def reais(c: int) -> str:
    return f"R$ {c // 100},{c % 100:02d}"


def ler_catalogo() -> list[dict[str, Any]]:
    with (pasta_trabalho() / "catalogo.csv").open(encoding="utf-8") as f:
        return [
            {"sku": r["sku"], "nome": r["nome"], "custo": centavos(r["custo"]), "preco": centavos(r["preco"])}
            for r in csv.DictReader(f)
        ]


def gravar_catalogo(produtos: list[dict[str, Any]]) -> None:
    with (pasta_trabalho() / "catalogo.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "nome", "custo", "preco"])
        for p in produtos:
            w.writerow([p["sku"], p["nome"], f"{p['custo'] / 100:.2f}", f"{p['preco'] / 100:.2f}"])


def ler_json(nome: str, padrao: Any) -> Any:
    arq = pasta_trabalho() / nome
    return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else padrao


def gravar_json(nome: str, dados: Any) -> None:
    (pasta_trabalho() / nome).write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


def preco_promocional(custo: int, preco: int, desconto_pct: int) -> tuple[int, str]:
    """Aplica o playbook da skill `promocao` (valores em centavos).

    Devolve (preço novo, situação) com situação em: "ok", "travou_na_margem", "sem_desconto".
    """
    alvo = preco * (100 - desconto_pct) // 100
    minimo = -(-custo * (100 + MARGEM_MINIMA_PCT) // 100)  # arredonda para cima
    novo = (alvo // 100) * 100 + 90
    if novo > alvo:
        novo -= 100
    situacao = "ok"
    while novo < minimo:
        novo += 100
        situacao = "travou_na_margem"
    if novo >= preco:
        return preco, "sem_desconto"
    return novo, situacao


def calcular_rascunho(
    desconto_pct: int,
    progresso: Any = None,
    cancelado: threading.Event | None = None,
    pausa: float | None = None,
) -> dict[str, Any]:
    """O trabalho "longo": recalcula o preço de cada produto e grava o rascunho."""
    if not 1 <= desconto_pct <= 90:
        raise ValueError("desconto_pct precisa ficar entre 1 e 90")
    pausa = float(os.environ.get("LOJA_PAUSA", "0.02")) if pausa is None else pausa
    produtos = ler_catalogo()
    total = len(produtos)
    itens, travados, sem_desconto = [], 0, 0
    for i, p in enumerate(produtos, start=1):
        if cancelado is not None and cancelado.is_set():
            raise InterruptedError("cancelado")
        novo, situacao = preco_promocional(p["custo"], p["preco"], desconto_pct)
        travados += situacao == "travou_na_margem"
        sem_desconto += situacao == "sem_desconto"
        if situacao != "sem_desconto":
            itens.append({"sku": p["sku"], "nome": p["nome"], "antes": p["preco"], "novo": novo})
        if pausa:
            time.sleep(pausa)
        if progresso is not None and (i % 50 == 0 or i == total):
            progresso(f"{i} de {total} produtos conferidos")
    rascunho = {"desconto_pct": desconto_pct, "itens": itens}
    gravar_json("rascunho.json", rascunho)
    return {
        "conferidos": total,
        "com_preco_novo": len(itens),
        "travados_na_margem": travados,
        "sem_desconto_possivel": sem_desconto,
    }


def texto_resumo(resumo: dict[str, Any]) -> str:
    return (
        f"{resumo['conferidos']} produtos conferidos. {resumo['com_preco_novo']} com preço novo no rascunho, "
        f"{resumo['travados_na_margem']} travados na margem mínima de {MARGEM_MINIMA_PCT}%, "
        f"{resumo['sem_desconto_possivel']} sem desconto possível. Nada foi publicado ainda: use publicar_precos."
    )


def resultado_tool(texto: str, estruturado: dict[str, Any] | None = None) -> dict[str, Any]:
    """Um CallToolResult no formato do fio (o `result` que a task entrega no fim)."""
    res: dict[str, Any] = {"content": [{"type": "text", "text": texto}], "isError": False}
    if estruturado is not None:
        res["structuredContent"] = estruturado
    return res


# ---------------------------------------------------------------------------
# Extensão 1: Skills over MCP (io.modelcontextprotocol/skills)
# ---------------------------------------------------------------------------


class UriParams(RequestParams):
    uri: str


class CursorParams(RequestParams):
    cursor: str | None = None


def _frontmatter(texto: str) -> dict[str, str]:
    if not texto.startswith("---\n"):
        raise ValueError("SKILL.md precisa começar com frontmatter YAML")
    bloco = texto[4 : texto.index("\n---", 4)]
    campos = {}
    for linha in bloco.splitlines():
        chave, _, valor = linha.partition(":")
        if chave.strip():
            campos[chave.strip()] = valor.strip()
    return campos


class SkillsExtension(Extension):
    """Entrega as skills da pasta `skills/` como `skill://<nome>/<arquivo>`."""

    identifier = SKILLS_ID
    CACHE = {"ttlMs": 300000, "cacheScope": "public"}

    def __init__(self, pasta: Path) -> None:
        self.arquivos: dict[str, tuple[str, str]] = {}  # uri -> (texto, mime)
        self.skills: list[dict[str, Any]] = []
        for skill_md in sorted(pasta.glob("*/SKILL.md")):
            raiz = skill_md.parent
            front = _frontmatter(skill_md.read_text(encoding="utf-8"))
            if front.get("name") != raiz.name:
                raise ValueError(f"name do frontmatter precisa ser '{raiz.name}'")
            manifesto = []
            for arq in sorted(p for p in raiz.rglob("*") if p.is_file()):
                rel = arq.relative_to(raiz).as_posix()
                uri = f"skill://{raiz.name}/{rel}"
                texto = arq.read_text(encoding="utf-8")
                bruto = texto.encode("utf-8")
                self.arquivos[uri] = (texto, "text/markdown" if arq.suffix == ".md" else "text/plain")
                manifesto.append(
                    {"uri": uri, "digest": "sha256:" + hashlib.sha256(bruto).hexdigest(), "size": len(bruto)}
                )
            manifesto.sort(key=lambda m: (not m["uri"].endswith("/SKILL.md"), m["uri"]))
            self.skills.append({"uri": f"skill://{raiz.name}/SKILL.md", "frontmatter": front, "resources": manifesto})

    def settings(self) -> dict[str, Any]:
        return {"directoryRead": True}

    def resources(self) -> list[ResourceBinding]:
        return [
            ResourceBinding(TextResource(uri=uri, name=uri.rsplit("/", 1)[-1], mime_type=mime, text=texto))
            for uri, (texto, mime) in self.arquivos.items()
        ]

    def methods(self) -> list[MethodBinding]:
        return [
            MethodBinding("skills/list", CursorParams, self._listar),
            MethodBinding("skills/get", UriParams, self._pegar),
            MethodBinding("resources/directory/read", UriParams, self._ler_pasta),
        ]

    async def _listar(self, ctx: Any, params: CursorParams) -> dict[str, Any]:
        return {"resultType": "complete", "skills": self.skills, **self.CACHE}

    async def _pegar(self, ctx: Any, params: UriParams) -> dict[str, Any]:
        for skill in self.skills:
            if skill["uri"] == params.uri:
                return {"resultType": "complete", "skill": skill, **self.CACHE}
        raise ValueError(f"skill não encontrada: {params.uri}")

    async def _ler_pasta(self, ctx: Any, params: UriParams) -> dict[str, Any]:
        base = params.uri.rstrip("/") + "/"
        filhos: dict[str, dict[str, str]] = {}
        for uri, (_, mime) in self.arquivos.items():
            if not uri.startswith(base):
                continue
            nome, _, resto = uri[len(base) :].partition("/")
            if resto:
                filhos[nome] = {"uri": base + nome, "name": nome, "mimeType": "inode/directory"}
            else:
                filhos[nome] = {"uri": uri, "name": nome, "mimeType": mime}
        if not filhos:
            raise ValueError(f"pasta não encontrada: {params.uri}")
        return {"resultType": "complete", "resources": list(filhos.values()), **self.CACHE}


# ---------------------------------------------------------------------------
# Extensão 2: Tasks (io.modelcontextprotocol/tasks)
# ---------------------------------------------------------------------------


class TaskIdParams(RequestParams):
    task_id: str


class TaskUpdateParams(RequestParams):
    task_id: str
    input_responses: dict[str, Any] = Field(default_factory=dict)


def _agora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def cliente_aceita_tasks(ctx: Any) -> bool:
    """A spec manda: só devolver task para quem declarou a extensão no pedido."""
    meta = getattr(ctx, "meta", None) or {}
    caps = meta.get(CLIENT_CAPS_META) if isinstance(meta, dict) else None
    if isinstance(caps, dict) and TASKS_ID in (caps.get("extensions") or {}):
        return True
    params = getattr(getattr(ctx, "session", None), "client_params", None)
    exts = getattr(getattr(params, "capabilities", None), "extensions", None) or {}
    return TASKS_ID in exts


class TasksExtension(Extension):
    """Transforma `atualizar_precos` em trabalho de segundo plano com polling."""

    identifier = TASKS_ID
    TOOLS_COM_TASK = {"atualizar_precos"}
    TTL_MS = 10 * 60 * 1000
    POLL_MS = 500

    def __init__(self) -> None:
        self._tarefas: dict[str, dict[str, Any]] = {}
        self._cancelar: dict[str, threading.Event] = {}
        self._trava = threading.Lock()

    def methods(self) -> list[MethodBinding]:
        return [
            MethodBinding("tasks/get", TaskIdParams, self._get),
            MethodBinding("tasks/update", TaskUpdateParams, self._update),
            MethodBinding("tasks/cancel", TaskIdParams, self._cancel),
        ]

    async def intercept_tool_call(self, params: Any, ctx: Any, call_next: Any) -> Any:
        if params.name not in self.TOOLS_COM_TASK or not cliente_aceita_tasks(ctx):
            return await call_next(ctx)  # cliente sem tasks: roda do jeito antigo, esperando
        desconto = int((params.arguments or {}).get("desconto_pct", 20))
        task_id = uuid.uuid4().hex[:12]
        agora = _agora()
        tarefa = {
            "taskId": task_id,
            "status": "working",
            "statusMessage": "começando",
            "createdAt": agora,
            "lastUpdatedAt": agora,
            "ttlMs": self.TTL_MS,
            "pollIntervalMs": self.POLL_MS,
        }
        cancelado = threading.Event()
        with self._trava:
            self._tarefas[task_id] = tarefa
            self._cancelar[task_id] = cancelado
        threading.Thread(target=self._rodar, args=(task_id, desconto, cancelado), daemon=True).start()
        return {"resultType": "task", **self._copia(task_id, detalhes=False)}

    def _mudar(self, task_id: str, **campos: Any) -> None:
        with self._trava:
            tarefa = self._tarefas[task_id]
            if tarefa["status"] in ("completed", "failed", "cancelled"):
                return
            tarefa.update(campos, lastUpdatedAt=_agora())

    def _rodar(self, task_id: str, desconto: int, cancelado: threading.Event) -> None:
        try:
            resumo = calcular_rascunho(desconto, lambda msg: self._mudar(task_id, statusMessage=msg), cancelado)
            self._mudar(
                task_id,
                status="completed",
                statusMessage="pronto",
                result=resultado_tool(texto_resumo(resumo), resumo),
            )
        except InterruptedError:
            self._mudar(task_id, status="cancelled", statusMessage="cancelado pelo cliente")
        except Exception as erro:  # noqa: BLE001 - vira status failed, como a spec pede
            self._mudar(task_id, status="failed", statusMessage=str(erro), error={"code": -32603, "message": str(erro)})

    def _copia(self, task_id: str, detalhes: bool = True) -> dict[str, Any]:
        with self._trava:
            tarefa = self._tarefas.get(task_id)
            if tarefa is None:
                raise ValueError(f"task não encontrada: {task_id}")
            copia = dict(tarefa)
        if not detalhes:
            copia.pop("result", None)
            copia.pop("error", None)
        return copia

    async def _get(self, ctx: Any, params: TaskIdParams) -> dict[str, Any]:
        return {"resultType": "complete", **self._copia(params.task_id)}

    async def _update(self, ctx: Any, params: TaskUpdateParams) -> dict[str, Any]:
        self._copia(params.task_id)  # esta tool não pede input no meio; respostas são ignoradas
        return {"resultType": "complete"}

    async def _cancel(self, ctx: Any, params: TaskIdParams) -> dict[str, Any]:
        self._copia(params.task_id)
        self._cancelar[params.task_id].set()
        return {"resultType": "complete"}


# ---------------------------------------------------------------------------
# Servidor e tools
# ---------------------------------------------------------------------------

mcp = MCPServer(
    name="loja",
    instructions=(
        "Lojinha na Black Friday. Antes de mexer em preço, carregue a skill skill://promocao/SKILL.md. "
        "atualizar_precos monta o rascunho (em segundo plano), publicar_precos pede confirmação ao usuário "
        "e apagar_produto exige que o usuário digite o nome do produto."
    ),
    extensions=[SkillsExtension(PASTA_SKILLS), TasksExtension()],
)


@mcp.tool(description="Recalcula o preço promocional de todo o catálogo (margem mínima 15%, final ,90). Só monta o rascunho; não publica.")
async def atualizar_precos(desconto_pct: int = 20) -> dict[str, Any]:
    # Caminho sem tasks (cliente não declarou a extensão): roda e espera.
    import anyio.to_thread

    resumo = await anyio.to_thread.run_sync(calcular_rascunho, desconto_pct)
    return {"resumo": texto_resumo(resumo), **resumo}


class Confirmacao(BaseModel):
    publicar: bool = Field(title="Publicar agora?", description="Sim publica na loja. Não deixa tudo como está.")


def _pergunta_publicar() -> Elicit[Confirmacao]:
    n = len(ler_json("rascunho.json", {"itens": []})["itens"])
    return Elicit(f"Publicar {n} preços novos agora?", Confirmacao)


@mcp.tool(description="Publica na loja os preços do rascunho. Sempre pergunta ao usuário antes (elicitation).")
async def publicar_precos(
    resposta: Annotated[ElicitationResult[Confirmacao], Resolve(_pergunta_publicar)],
) -> str:
    rascunho = ler_json("rascunho.json", {"itens": []})
    if not rascunho["itens"]:
        return "Não há rascunho. Rode atualizar_precos primeiro. Nada publicado."
    if not (isinstance(resposta, AcceptedElicitation) and resposta.data.publicar):
        return "Usuário não confirmou. Nada publicado."
    novos = {i["sku"]: i["novo"] for i in rascunho["itens"]}
    produtos = ler_catalogo()
    for p in produtos:
        p["preco"] = novos.get(p["sku"], p["preco"])
    gravar_catalogo(produtos)
    gravar_json("publicados.json", {"quando": _agora(), "itens": rascunho["itens"]})
    gravar_json("rascunho.json", {"itens": []})
    return f"{len(novos)} preços publicados na loja."


class NomeDigitado(BaseModel):
    nome: str = Field(title="Nome do produto", description="Digite o nome exato para confirmar")


def _achar(sku: str) -> dict[str, Any]:
    for p in ler_catalogo():
        if p["sku"] == sku:
            return p
    raise ToolError(f"Produto {sku} não existe.")


def _pergunta_apagar(sku: str) -> Elicit[NomeDigitado]:
    p = _achar(sku)
    return Elicit(f"Apagar não tem volta. Digite o nome exato: {p['nome']}", NomeDigitado)


@mcp.tool(description="Apaga um produto do catálogo. Destrutivo: exige que o usuário digite o nome exato do produto.")
async def apagar_produto(
    sku: str,
    resposta: Annotated[ElicitationResult[NomeDigitado], Resolve(_pergunta_apagar)],
) -> str:
    produto = _achar(sku)
    if not isinstance(resposta, AcceptedElicitation):
        return f"Usuário cancelou. {sku} continua na loja."
    if resposta.data.nome.strip() != produto["nome"]:
        return f"Nome não confere ('{resposta.data.nome}'). {sku} continua na loja."
    gravar_catalogo([p for p in ler_catalogo() if p["sku"] != sku])
    return f"{sku} ({produto['nome']}) apagado."


if __name__ == "__main__":
    mcp.run()
