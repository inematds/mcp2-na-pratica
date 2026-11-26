"""Transforma a saída colorida do demo.py em PNGs 1920x1080 (tela de vídeo).

    .venv/bin/python demo.py --auto --ritmo 0 > /tmp/demo-cor.txt
    python3 ferramentas/terminal_png.py /tmp/demo-cor.txt exemplos/

Gera demo-terminal.png (tudo, em duas colunas) e passo1-skill.png,
passo2-task.png, passo3-pergunta.png (um por passo, letra grande).
Precisa só do Pillow (`pip install pillow`).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LARGURA, ALTURA = 1920, 1080
FUNDO = "#0c0c10"
BARRA = "#16161d"
TEXTO = "#e8e8ea"
CORES = {"93": "#FACC15", "92": "#4ade80", "91": "#f87171", "96": "#67e8f9", "90": "#8b8b96", "97": "#ffffff"}
FONTES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
]
SGR = re.compile(r"\x1b\[([0-9;]*)m")


def segmentos(linha: str) -> list[tuple[str, str, bool]]:
    """Quebra uma linha com códigos ANSI em (texto, cor, negrito)."""
    saida, cor, negrito, pos = [], TEXTO, False, 0
    for m in SGR.finditer(linha):
        if m.start() > pos:
            saida.append((linha[pos : m.start()], cor, negrito))
        codigos = m.group(1).split(";") if m.group(1) else ["0"]
        for c in codigos:
            if c == "0":
                cor, negrito = TEXTO, False
            elif c == "1":
                negrito = True
            elif c in CORES:
                cor = CORES[c]
        pos = m.end()
    if pos < len(linha):
        saida.append((linha[pos:], cor, negrito))
    return saida


def visivel(linha: str) -> str:
    return SGR.sub("", linha)


def desenhar(colunas: list[list[str]], destino: Path, titulo: str) -> None:
    normal, negrito = FONTES[0]
    topo, margem, espaco_col = 70, 60, 70
    linhas_max = max(len(c) for c in colunas)
    larg_max = max(len(visivel(l)) for c in colunas for l in c) or 1
    # maior fonte que cabe na largura e na altura
    for tam in range(40, 12, -1):
        f = ImageFont.truetype(normal, tam)
        cw = f.getlength("M")
        lh = int(tam * 1.42)
        largura_total = len(colunas) * larg_max * cw + (len(colunas) - 1) * espaco_col
        if largura_total <= LARGURA - 2 * margem and linhas_max * lh <= ALTURA - topo - 40:
            break
    fn, fb = ImageFont.truetype(normal, tam), ImageFont.truetype(negrito, tam)
    img = Image.new("RGB", (LARGURA, ALTURA), FUNDO)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, LARGURA, 46], fill=BARRA)
    for i, cor in enumerate(("#f87171", "#FACC15", "#4ade80")):
        d.ellipse([24 + i * 30, 15, 40 + i * 30, 31], fill=cor)
    ft = ImageFont.truetype(normal, 20)
    d.text((LARGURA / 2, 23), titulo, font=ft, fill="#8b8b96", anchor="mm")
    x0 = (LARGURA - (len(colunas) * larg_max * cw + (len(colunas) - 1) * espaco_col)) / 2
    for ci, coluna in enumerate(colunas):
        x_col = x0 + ci * (larg_max * cw + espaco_col)
        y = topo + (ALTURA - topo - 40 - len(coluna) * lh) / 2
        for linha in coluna:
            x = x_col
            for texto, cor, bold in segmentos(linha):
                fonte = fb if bold else fn
                for pedaco in re.split(r"([█░]+)", texto):
                    if pedaco and pedaco[0] in "█░":  # barra de progresso: retângulos lisos
                        for ch in pedaco:
                            d.rectangle([x, y + lh * 0.12, x + cw, y + lh * 0.78], fill=cor if ch == "█" else "#2a2a33")
                            x += cw
                    elif pedaco:
                        d.text((x, y), pedaco, font=fonte, fill=cor)
                        x += fonte.getlength(pedaco)
            y += lh
    img.save(destino)


def main() -> None:
    origem, pasta = Path(sys.argv[1]), Path(sys.argv[2])
    linhas = origem.read_text(encoding="utf-8").rstrip("\n").split("\n")
    inicios = [i for i, l in enumerate(linhas) if "PASSO " in visivel(l) and " DE 3" in visivel(l)]
    cabeca = linhas[: inicios[0]]
    passos = [linhas[a:b] for a, b in zip(inicios, inicios[1:] + [len(linhas)])]
    passos = [[l for l in p] for p in passos]
    while passos[-1] and not visivel(passos[-1][-1]).strip():
        passos[-1].pop()
    fim = [l for l in passos[-1] if visivel(l).startswith("FIM")]
    passos[-1] = [l for l in passos[-1] if not visivel(l).startswith("FIM")]
    for p in passos:
        while p and not visivel(p[-1]).strip():
            p.pop()

    titulo = "loja — .venv/bin/python demo.py --auto"
    esquerda = cabeca + passos[0] + [""] + passos[1]
    direita = passos[2] + [""] + fim
    desenhar([esquerda, direita], pasta / "demo-terminal.png", titulo)
    nomes = ["passo1-skill.png", "passo2-task.png", "passo3-pergunta.png"]
    for nome, passo in zip(nomes, passos):
        desenhar([passo], pasta / nome, titulo)
    print("PNGs gravados em", pasta)


if __name__ == "__main__":
    main()
