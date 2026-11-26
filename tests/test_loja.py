"""Testes do kit: Skills, Tasks, Elicitation e as recusas.

Tudo roda contra o servidor de verdade, por stdio (subprocesso), numa pasta
de trabalho temporária. O CSV de exemplo nunca é alterado.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp_types import ElicitResult

KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))

import servidor  # noqa: E402
from loja_cliente import ClienteTasks, conferir_skill, parametros_servidor, pedir  # noqa: E402


def rodar(coro: Any) -> Any:
    return asyncio.run(asyncio.wait_for(coro, timeout=60))


def respondendo(*respostas: dict[str, Any]):
    """Callback de elicitation que devolve respostas prontas e guarda as perguntas."""
    fila = list(respostas)
    perguntas: list[Any] = []

    async def callback(ctx: Any, params: Any) -> ElicitResult:
        perguntas.append(params)
        return ElicitResult(**fila.pop(0))

    callback.perguntas = perguntas  # type: ignore[attr-defined]
    return callback


def catalogo(pasta: Path) -> dict[str, dict[str, str]]:
    with (pasta / "catalogo.csv").open(encoding="utf-8") as f:
        return {r["sku"]: r for r in csv.DictReader(f)}


def ligar(pasta: Path, **kwargs: Any) -> Client:
    return Client(parametros_servidor(pasta, pausa="0"), **kwargs)


# --- regras da skill (função pura) --------------------------------------------


@pytest.mark.parametrize(
    ("custo", "preco", "esperado", "situacao"),
    [
        (1200, 3990, 3190, "ok"),  # caneca da tabela de exemplos
        (8000, 9990, 9290, "travou_na_margem"),  # fone: margem mínima segura
        (2500, 5990, 4790, "ok"),  # camiseta
        (9000, 9990, 9990, "sem_desconto"),  # mínimo passa do preço atual
    ],
)
def test_regras_da_promocao(custo: int, preco: int, esperado: int, situacao: str) -> None:
    novo, sit = servidor.preco_promocional(custo, preco, 20)
    assert (novo, sit) == (esperado, situacao)
    if sit != "sem_desconto":
        assert novo % 100 == 90
        assert novo >= custo * 1.15


# --- 1. Skills ----------------------------------------------------------------


def test_skill_promocao_listada_lida_e_conferida(tmp_path: Path) -> None:
    async def caso() -> None:
        async with ligar(tmp_path) as client:
            exts = client.server_capabilities.extensions or {}
            assert exts["io.modelcontextprotocol/skills"] == {"directoryRead": True}
            assert client.server_capabilities.resources is not None

            lista = await pedir(client, "skills/list")
            assert lista["resultType"] == "complete" and lista["ttlMs"] > 0 and lista["cacheScope"]
            [entrada] = lista["skills"]
            assert entrada["uri"] == "skill://promocao/SKILL.md"
            assert entrada["frontmatter"]["name"] == "promocao"

            textos = await conferir_skill(client, entrada)  # confere tamanho e SHA-256
            assert "Margem mínima de 15%" in textos["skill://promocao/SKILL.md"]
            disco = (KIT / "skills/promocao/SKILL.md").read_bytes()
            assert entrada["resources"][0]["digest"] == "sha256:" + hashlib.sha256(disco).hexdigest()

            unica = await pedir(client, "skills/get", uri="skill://promocao/SKILL.md")
            assert unica["skill"] == entrada

            pasta = await pedir(client, "resources/directory/read", uri="skill://promocao")
            nomes = {r["name"]: r["mimeType"] for r in pasta["resources"]}
            assert nomes == {"SKILL.md": "text/markdown", "references": "inode/directory"}

    rodar(caso())


# --- 2. Tasks -----------------------------------------------------------------


def test_atualizar_precos_vira_task_com_polling(tmp_path: Path) -> None:
    tasks = ClienteTasks()

    async def caso() -> Any:
        async with Client(parametros_servidor(tmp_path, pausa="0.005"), extensions=[tasks]) as client:
            return await client.call_tool("atualizar_precos", {"desconto_pct": 20})

    resultado = rodar(caso())
    criada, *polls = tasks.historico
    assert criada["status"] == "working" and criada["ttlMs"] and criada["pollIntervalMs"]
    assert polls and polls[-1]["status"] == "completed"
    assert any("de 300" in p.get("statusMessage", "") for p in polls)
    assert resultado.structured_content["conferidos"] == 300
    rascunho = json.loads((tmp_path / "rascunho.json").read_text(encoding="utf-8"))
    assert len(rascunho["itens"]) == resultado.structured_content["com_preco_novo"]
    assert all(i["novo"] % 100 == 90 and i["novo"] < i["antes"] for i in rascunho["itens"])


def test_sem_extensao_de_tasks_roda_do_jeito_antigo(tmp_path: Path) -> None:
    async def caso() -> Any:
        async with ligar(tmp_path) as client:  # cliente NÃO declara a extensão
            return await client.call_tool("atualizar_precos", {"desconto_pct": 20})

    resultado = rodar(caso())
    assert resultado.structured_content["conferidos"] == 300
    assert (tmp_path / "rascunho.json").exists()


def test_task_cancelada(tmp_path: Path) -> None:
    tasks = ClienteTasks()

    async def caso() -> Any:
        async with Client(parametros_servidor(tmp_path, pausa="0.05"), extensions=[tasks]) as client:

            async def cancelar(task: dict[str, Any]) -> None:
                await pedir(client, "tasks/cancel", taskId=task["taskId"])

            tasks.ao_criar = cancelar
            return await client.call_tool("atualizar_precos", {"desconto_pct": 20})

    resultado = rodar(caso())
    assert tasks.historico[-1]["status"] == "cancelled"
    assert resultado.is_error
    assert not (tmp_path / "rascunho.json").exists()


# --- 3. Elicitation -----------------------------------------------------------


def preparar_rascunho(pasta: Path) -> int:
    import os

    os.environ["LOJA_TRABALHO"] = str(pasta)
    try:
        return servidor.calcular_rascunho(20, pausa=0)["com_preco_novo"]
    finally:
        del os.environ["LOJA_TRABALHO"]


def test_publicar_pergunta_e_publica_quando_sim(tmp_path: Path) -> None:
    n = preparar_rascunho(tmp_path)
    antes = catalogo(tmp_path)
    cb = respondendo({"action": "accept", "content": {"publicar": True}})

    async def caso() -> Any:
        async with ligar(tmp_path, elicitation_callback=cb) as client:
            return await client.call_tool("publicar_precos", {})

    r = rodar(caso())
    [pergunta] = cb.perguntas
    assert pergunta.message == f"Publicar {n} preços novos agora?"
    assert pergunta.requested_schema["properties"]["publicar"]["type"] == "boolean"
    assert r.content[0].text == f"{n} preços publicados na loja."
    assert (tmp_path / "publicados.json").exists()
    assert catalogo(tmp_path) != antes


@pytest.mark.parametrize(
    "resposta",
    [
        {"action": "accept", "content": {"publicar": False}},
        {"action": "decline"},
        {"action": "cancel"},
    ],
)
def test_recusa_nada_publicado(tmp_path: Path, resposta: dict[str, Any]) -> None:
    preparar_rascunho(tmp_path)
    antes = catalogo(tmp_path)

    async def caso() -> Any:
        async with ligar(tmp_path, elicitation_callback=respondendo(resposta)) as client:
            return await client.call_tool("publicar_precos", {})

    r = rodar(caso())
    assert "Nada publicado" in r.content[0].text
    assert not (tmp_path / "publicados.json").exists()
    assert catalogo(tmp_path) == antes


def test_cliente_sem_elicitation_nao_publica(tmp_path: Path) -> None:
    preparar_rascunho(tmp_path)
    antes = catalogo(tmp_path)

    async def caso() -> Any:
        async with ligar(tmp_path) as client:  # sem elicitation_callback
            return await client.call_tool("publicar_precos", {})

    # O SDK recusa no servidor: o cliente não declarou a capacidade de elicitation.
    with pytest.raises(BaseException) as erro:
        rodar(caso())
    assert "elicitation capability" in "".join(traceback.format_exception(erro.value))
    assert not (tmp_path / "publicados.json").exists()
    assert catalogo(tmp_path) == antes


def test_apagar_com_nome_errado_nao_apaga(tmp_path: Path) -> None:
    cb = respondendo({"action": "accept", "content": {"nome": "Caneca"}})

    async def caso() -> Any:
        async with ligar(tmp_path, elicitation_callback=cb) as client:
            return await client.call_tool("apagar_produto", {"sku": "SKU001"})

    r = rodar(caso())
    assert "Caneca Azul P" in cb.perguntas[0].message
    assert "continua na loja" in r.content[0].text
    assert "SKU001" in catalogo(tmp_path)


def test_apagar_com_nome_certo_apaga(tmp_path: Path) -> None:
    cb = respondendo({"action": "accept", "content": {"nome": "Caneca Azul P"}})

    async def caso() -> Any:
        async with ligar(tmp_path, elicitation_callback=cb) as client:
            return await client.call_tool("apagar_produto", {"sku": "SKU001"})

    r = rodar(caso())
    assert "apagado" in r.content[0].text
    assert "SKU001" not in catalogo(tmp_path)
    assert len(catalogo(tmp_path)) == 299


def test_protocolo_antigo_tambem_pergunta(tmp_path: Path) -> None:
    """Handshake antigo (initialize): a pergunta vai pelo canal de volta, mesmo resultado."""
    cb = respondendo({"action": "accept", "content": {"nome": "errado"}})

    async def caso() -> tuple[str, Any]:
        async with ligar(tmp_path, elicitation_callback=cb, mode="legacy") as client:
            return client.protocol_version, await client.call_tool("apagar_produto", {"sku": "SKU002"})

    versao, r = rodar(caso())
    assert versao != "2026-07-28"
    assert "continua na loja" in r.content[0].text
    assert "SKU002" in catalogo(tmp_path)


def test_csv_de_exemplo_intacto() -> None:
    with (KIT / "exemplos/produtos.csv").open(encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    assert len(linhas) == 300 and linhas[0]["nome"] == "Caneca Azul P"
