"""
Leitor serial - Atividade Acelerometro (FRDM-KL25Z)

Captura as linhas enviadas pela placa no formato
    t_ms;ax;ay;az;vx;vy;vz;px;py;pz
e grava em um arquivo .csv com aceleracao, velocidade e posicao.

Uso:
    pip install pyserial
    python leitor_serial.py                 # usa PORTA e ARQUIVO abaixo
    python leitor_serial.py COM5 dados.csv  # ou passe pela linha de comando

Pare com Ctrl+C.
"""
import csv
import sys
import time

import serial

PORTA = "COM3"            # Windows: COMx (veja no Gerenciador de Dispositivos)
                          # Linux: /dev/ttyACM0  |  macOS: /dev/cu.usbmodemXXXX
BAUD = 115200
ARQUIVO = "dados_acelerometro.csv"

CABECALHO = ["t_s", "ax", "ay", "az", "vx", "vy", "vz", "px", "py", "pz"]


def main():
    porta = sys.argv[1] if len(sys.argv) > 1 else PORTA
    arquivo = sys.argv[2] if len(sys.argv) > 2 else ARQUIVO

    ser = serial.Serial(porta, BAUD, timeout=1)
    print(f"Lendo {porta} @ {BAUD} -> {arquivo}  (Ctrl+C para parar)")

    t0 = None
    n = 0
    with open(arquivo, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CABECALHO)
        try:
            while True:
                linha = ser.readline().decode("ascii", errors="ignore").strip()
                if not linha:
                    continue
                if linha.startswith("#") or linha.startswith("t_ms"):
                    print(linha)          # mensagens de calibracao / cabecalho
                    continue
                campos = linha.split(";")
                if len(campos) != 10:
                    continue              # linha incompleta
                try:
                    valores = [float(c) for c in campos]
                except ValueError:
                    continue
                if t0 is None:
                    t0 = valores[0]
                valores[0] = (valores[0] - t0) / 1000.0   # ms -> s, comeca em 0
                w.writerow([f"{v:.4f}" for v in valores])
                n += 1
                if n % 50 == 0:
                    f.flush()
                    print(f"{n} amostras | a=({valores[1]:+.2f},{valores[2]:+.2f},{valores[3]:+.2f}) "
                          f"v=({valores[4]:+.3f},{valores[5]:+.3f},{valores[6]:+.3f}) "
                          f"p=({valores[7]:+.3f},{valores[8]:+.3f},{valores[9]:+.3f})")
        except KeyboardInterrupt:
            pass
    ser.close()
    print(f"\n{n} amostras salvas em {arquivo}")


if __name__ == "__main__":
    main()
