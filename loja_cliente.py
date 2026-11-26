"""Peças de cliente MCP usadas pelo demo.py e pelos testes.

O SDK `mcp` 2.3.0 sabe responder elicitation (callback) e tem o encanamento
de extensões no cliente (`ClientExtension` + `ResultClaim`), mas não traz o
cliente de tasks nem de skills. Aqui está o mínimo dos dois.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from mcp import Client, StdioServerParameters
from mcp.client.extension import ClaimContext, ClientExtension, ResultClaim
from mcp_types import CallToolResult, Request, RequestParams, Result
from pydantic import ConfigDict

KIT = Path(__file__).resolve().parent
TASKS_ID = "io.modelcontextprotocol/tasks"
SKILLS_ID = "io.modelcontextprotocol/skills"
TERMINAIS = ("completed", "failed", "cancelled")


class ResultadoLivre(Result):
    """Resultado de método de extensão (o SDK não tem modelo para eles)."""

    model_config = ConfigDict(extra="allow")


class ParamsLivres(RequestParams):
    model_config = ConfigDict(extra="allow")


class PedidoExtensao(Request[ParamsLivres, str]):
    method: str
    params: ParamsLivres


async def pedir(client: Client, metodo: str, **params: Any) -> dict[str, Any]:
    """Manda um pedido de extensão (skills/list, tasks/get...) e devolve o JSON do fio."""
    resposta = await client.session.send_request(
        PedidoExtensao(method=metodo, params=ParamsLivres(**params)), ResultadoLivre
    )
    dados = resposta.model_dump(by_alias=True, exclude_none=True)
    dados.pop("_meta", None)
    return dados


# --- Tasks -----------------------------------------------------------------


class TaskCriada(Result):
    """O `CreateTaskResult` (resultType "task") que o servidor devolve no tools/call."""

    model_config = ConfigDict(extra="allow")
    result_type: Literal["task"] = "task"


AoMudar = Callable[[dict[str, Any]], Awaitable[None] | None]


class ClienteTasks(ClientExtension):
    """Declara a extensão de tasks e faz o polling `tasks/get` até o fim."""

    identifier = TASKS_ID

    def __init__(self, ao_mudar: AoMudar | None = None, ao_criar: AoMudar | None = None) -> None:
        self.ao_mudar = ao_mudar
        self.ao_criar = ao_criar
        self.historico: list[dict[str, Any]] = []

    def claims(self) -> list[ResultClaim[Any]]:
        return [ResultClaim(result_type="task", model=TaskCriada, resolve=self._acompanhar)]

    async def _avisar(self, funcao: AoMudar | None, dados: dict[str, Any]) -> None:
        if funcao is not None:
            retorno = funcao(dados)
            if asyncio.iscoroutine(retorno):
                await retorno

    async def _acompanhar(self, criada: TaskCriada, ctx: ClaimContext) -> CallToolResult:
        task = criada.model_dump(by_alias=True, exclude_none=True)
        task.pop("_meta", None)
        self.historico.append(task)
        await self._avisar(self.ao_criar, task)
        ultimo = None
        while True:
            await asyncio.sleep(task.get("pollIntervalMs", 500) / 1000)
            resposta = await ctx.session.send_request(
                PedidoExtensao(method="tasks/get", params=ParamsLivres(taskId=task["taskId"])), ResultadoLivre
            )
            task = resposta.model_dump(by_alias=True, exclude_none=True)
            task.pop("_meta", None)
            self.historico.append(task)
            chave = (task["status"], task.get("statusMessage"))
            if chave != ultimo:
                ultimo = chave
                await self._avisar(self.ao_mudar, task)
            if task["status"] == "completed":
                return CallToolResult.model_validate(task["result"])
            if task["status"] in ("failed", "cancelled"):
                msg = task.get("error", {}).get("message") or task.get("statusMessage") or task["status"]
                return CallToolResult(content=[{"type": "text", "text": f"task {task['status']}: {msg}"}], is_error=True)


# --- Skills ----------------------------------------------------------------


async def conferir_skill(client: Client, entrada: dict[str, Any]) -> dict[str, str]:
    """Lê cada arquivo do manifesto e confere tamanho e SHA-256, como a spec manda."""
    textos = {}
    for item in entrada["resources"]:
        lido = await client.read_resource(item["uri"])
        texto = lido.contents[0].text
        bruto = texto.encode("utf-8")
        if len(bruto) != item["size"] or "sha256:" + hashlib.sha256(bruto).hexdigest() != item["digest"]:
            raise ValueError(f"arquivo não confere com o manifesto: {item['uri']}")
        textos[item["uri"]] = texto
    return textos


# --- Ligar o servidor --------------------------------------------------------


def parametros_servidor(pasta_trabalho: str | Path, pausa: str | None = None) -> StdioServerParameters:
    env = {**os.environ, "LOJA_TRABALHO": str(pasta_trabalho)}
    if pausa is not None:
        env["LOJA_PAUSA"] = pausa
    return StdioServerParameters(command=sys.executable, args=[str(KIT / "servidor.py")], env=env)
