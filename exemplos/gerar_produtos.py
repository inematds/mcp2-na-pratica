"""Gera exemplos/produtos.csv: 300 produtos fictícios de uma lojinha (sempre os mesmos)."""

import csv
import random
from pathlib import Path

TIPOS = [
    ("Caneca", 8, 20), ("Camiseta", 18, 35), ("Fone", 40, 120), ("Mochila", 45, 110),
    ("Garrafa", 10, 25), ("Capinha", 5, 15), ("Luminária", 30, 80), ("Agenda", 9, 22),
    ("Boné", 12, 30), ("Carregador", 20, 60), ("Toalha", 15, 40), ("Chinelo", 10, 28),
]
CORES = ["Azul", "Preto", "Branco", "Verde", "Vermelho", "Amarelo", "Rosa", "Cinza", "Lilás", "Laranja"]
TAMANHOS = ["P", "M", "G"]


def gerar(destino: Path, total: int = 300) -> None:
    rnd = random.Random(2026)
    linhas = []
    for i in range(total):
        tipo, cmin, cmax = TIPOS[i % len(TIPOS)]
        cor = CORES[(i // len(TIPOS)) % len(CORES)]
        tam = TAMANHOS[(i // (len(TIPOS) * len(CORES))) % len(TAMANHOS)]
        custo = round(rnd.uniform(cmin, cmax), 2)
        # margem de venda entre 20% e 160%; algumas ficam apertadas de propósito
        preco = int(custo * rnd.uniform(1.2, 2.6)) + 0.90
        linhas.append([f"SKU{i + 1:03d}", f"{tipo} {cor} {tam}", f"{custo:.2f}", f"{preco:.2f}"])
    with destino.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku", "nome", "custo", "preco"])
        w.writerows(linhas)


if __name__ == "__main__":
    gerar(Path(__file__).with_name("produtos.csv"))
