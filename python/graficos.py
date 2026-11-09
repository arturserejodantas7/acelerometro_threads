"""
Gera o grafico de aceleracao, velocidade e posicao a partir do .csv
gravado pelo leitor_serial.py.

Uso:
    pip install matplotlib
    python graficos.py dados_acelerometro.csv          # salva grafico.png
    python graficos.py dados_acelerometro.csv saida.png
"""
import csv
import sys

import matplotlib.pyplot as plt


def carregar(arquivo):
    cols = {k: [] for k in ["t_s", "ax", "ay", "az", "vx", "vy", "vz", "px", "py", "pz"]}
    with open(arquivo, newline="") as f:
        for linha in csv.DictReader(f):
            for k in cols:
                cols[k].append(float(linha[k]))
    return cols


def plotar(d, saida, titulo="Acelerometro MMA8451Q - FRDM-KL25Z"):
    fig, ax = plt.subplots(3, 1, figsize=(9, 9), sharex=True)
    cores = {"x": "#1f77b4", "y": "#d62728", "z": "#2ca02c"}
    grandezas = [("a", "Aceleracao (m/s²)"), ("v", "Velocidade (m/s)"), ("p", "Posicao (m)")]
    for eixo, (g, rot) in zip(ax, grandezas):
        for c in "xyz":
            eixo.plot(d["t_s"], d[g + c], label=c, color=cores[c], lw=1.2)
        eixo.set_ylabel(rot)
        eixo.grid(alpha=0.3)
        eixo.legend(loc="upper right", ncol=3, fontsize=8)
    ax[-1].set_xlabel("Tempo (s)")
    fig.suptitle(titulo)
    fig.tight_layout()
    fig.savefig(saida, dpi=150)
    print(f"Grafico salvo em {saida}")


if __name__ == "__main__":
    arq = sys.argv[1] if len(sys.argv) > 1 else "dados_acelerometro.csv"
    out = sys.argv[2] if len(sys.argv) > 2 else "grafico.png"
    plotar(carregar(arq), out)
    plt.show()
