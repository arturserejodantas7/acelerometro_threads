"""
Validacao do algoritmo de integracao (mesmas equacoes do firmware) com um
movimento conhecido: a placa e deslocada 0,30 m em x e volta ao ponto inicial.

Gera:
  - simulacao.csv           (mesmo formato do leitor_serial.py)
  - validacao_integracao.png (exato x trapezio x Simpson)

ATENCAO: sao dados SIMULADOS, servem para validar o metodo numerico.
O grafico a entregar deve ser gerado com os dados reais da placa.
"""
import csv

import numpy as np
import matplotlib.pyplot as plt

DT = 0.01
ZONA_MORTA = 0.05
LIMIAR_PARADO = 0.10
N_PARADO = 50
RUIDO = 0.02          # m/s^2 (desvio padrao)
BIAS = np.array([0.01, -0.008, 0.012])   # offset residual apos calibracao

t = np.arange(0, 7.0, DT)
w = np.pi / 2
A = 0.15


def mov(tt):
    """posicao, velocidade e aceleracao exatas em x"""
    x = np.zeros_like(tt); v = np.zeros_like(tt); a = np.zeros_like(tt)
    ida = (tt >= 1) & (tt < 3)
    tau = tt[ida] - 1
    x[ida] = A * (1 - np.cos(w * tau)); v[ida] = A * w * np.sin(w * tau); a[ida] = A * w**2 * np.cos(w * tau)
    x[(tt >= 3) & (tt < 4)] = 2 * A
    volta = (tt >= 4) & (tt < 6)
    tau = tt[volta] - 4
    x[volta] = 2 * A - A * (1 - np.cos(w * tau)); v[volta] = -A * w * np.sin(w * tau); a[volta] = -A * w**2 * np.cos(w * tau)
    return x, v, a


x_ex, v_ex, a_ex = mov(t)
rng = np.random.default_rng(1)
a_med = np.zeros((len(t), 3))
a_med[:, 0] = a_ex
a_med += BIAS + rng.normal(0, RUIDO, a_med.shape)
a_med = a_med.astype(np.float32)


def integrar(a_in, simpson, zupt=True):
    """Copia fiel do laco da thread de integracao do firmware."""
    n_am = len(a_in)
    V = np.zeros((n_am, 3), np.float32); P = np.zeros((n_am, 3), np.float32)
    a0 = np.zeros(3, np.float32); a1 = np.zeros(3, np.float32)
    v0 = np.zeros(3, np.float32); v1 = np.zeros(3, np.float32)
    v = np.zeros(3, np.float32); p = np.zeros(3, np.float32)
    parado = 0
    dt = np.float32(DT)
    A_out = np.zeros_like(a_in)
    for n in range(n_am):
        s = a_in[n].copy()
        quieto = True
        for i in range(3):
            if abs(s[i]) >= LIMIAR_PARADO:
                quieto = False
            if abs(s[i]) < ZONA_MORTA:
                s[i] = 0
        if n > 0:
            for i in range(3):
                if simpson and n % 2 == 0:
                    vn = v0[i] + dt / 3 * (a0[i] + 4 * a1[i] + s[i])
                else:
                    vn = v1[i] + 0.5 * dt * (a1[i] + s[i])
                p[i] += 0.5 * dt * (v1[i] + vn)
                v[i] = vn
        parado = parado + 1 if quieto else 0
        if zupt and parado >= N_PARADO:
            v[:] = 0
        a0, a1 = a1.copy(), s.copy()
        v0, v1 = v1.copy(), v.copy()
        V[n], P[n], A_out[n] = v, p, s
    return A_out, V, P


A_tr, V_tr, P_tr = integrar(a_med, simpson=False)
_, V_si, P_si = integrar(a_med, simpson=True)
_, V_raw, P_raw = integrar(a_med, simpson=False, zupt=False)

# Exato com a mesma deriva de nada: referencia
print(f"Erro final de posicao x  trapezio: {abs(P_tr[-1,0]-x_ex[-1])*100:.2f} cm")
print(f"Erro final de posicao x  Simpson : {abs(P_si[-1,0]-x_ex[-1])*100:.2f} cm")
print(f"Erro max posicao x       trapezio: {np.max(abs(P_tr[:,0]-x_ex))*100:.2f} cm")
print(f"Erro max posicao x       Simpson : {np.max(abs(P_si[:,0]-x_ex))*100:.2f} cm")
print(f"Sem zona morta/ZUPT, deriva em z apos 7 s: {P_raw[-1,2]*100:.2f} cm (x: {(P_raw[-1,0]-x_ex[-1])*100:.2f} cm)")

# CSV no formato do leitor (decimado para 50 Hz, como a thread serial)
with open("simulacao.csv", "w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["t_s", "ax", "ay", "az", "vx", "vy", "vz", "px", "py", "pz"])
    for n in range(0, len(t), 2):
        wr.writerow([f"{t[n]:.4f}"] + [f"{v:.4f}" for v in (*A_tr[n], *V_tr[n], *P_tr[n])])

fig, ax = plt.subplots(3, 1, figsize=(9, 9), sharex=True)
ax[0].plot(t, a_med[:, 0], color="#bbbbbb", lw=0.8, label="medida (ruido + offset)")
ax[0].plot(t, A_tr[:, 0], color="#1f77b4", lw=1.0, label="apos zona morta")
ax[0].plot(t, a_ex, "k--", lw=1.0, label="exata")
ax[0].set_ylabel("ax (m/s²)")
ax[1].plot(t, v_ex, "k--", lw=1.2, label="exata")
ax[1].plot(t, V_tr[:, 0], color="#1f77b4", lw=1.2, label="trapezio")
ax[1].plot(t, V_si[:, 0], color="#d62728", lw=1.0, ls=":", label="Simpson 1/3")
ax[1].plot(t, V_raw[:, 0], color="#999999", lw=1.0, label="trapezio sem zona morta/ZUPT")
ax[1].set_ylabel("vx (m/s)")
ax[2].plot(t, x_ex, "k--", lw=1.2, label="exata")
ax[2].plot(t, P_tr[:, 0], color="#1f77b4", lw=1.2, label="trapezio")
ax[2].plot(t, P_si[:, 0], color="#d62728", lw=1.0, ls=":", label="Simpson 1/3")
ax[2].plot(t, P_raw[:, 0], color="#999999", lw=1.0, label="trapezio sem zona morta/ZUPT")
ax[2].set_ylabel("px (m)")
ax[2].set_xlabel("Tempo (s)")
for e in ax:
    e.grid(alpha=0.3); e.legend(fontsize=8, loc="upper right")
fig.suptitle("Validacao da integracao numerica (dados SIMULADOS, 100 Hz)")
fig.tight_layout()
fig.savefig("validacao_integracao.png", dpi=150)
print("ok")
