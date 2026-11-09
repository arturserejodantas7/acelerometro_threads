# Atividade Acelerômetro – Serial (com threads)

FRDM-KL25Z + MMA8451Q (I²C0, endereço 0x1D) + Zephyr.

## Threads

| Thread | Prioridade | Ativação | Função |
|---|---|---|---|
| `t_aquisicao` | 5 (maior) | periódica, 10 ms (`k_timer`) | lê o MMA8451Q, converte para m/s², remove offset, publica na `k_msgq` |
| `t_integracao` | 6 | por evento (chegada na `k_msgq`) | integra a → v → x (trapézio; Simpson 1/3 com `INTEGRADOR_SIMPSON 1`) |
| `t_serial` | 7 (menor) | periódica, 20 ms (`k_sleep` absoluto) | copia o estado (mutex) e envia `t_ms;ax;ay;az;vx;vy;vz;px;py;pz` |

## Compilar e gravar (PlatformIO)

Abra a pasta no VS Code com a extensão PlatformIO e use **Build** (✓) e **Upload** (→)
na barra inferior, ou no terminal:

```
pio run -t upload
```

Estrutura exigida pelo PlatformIO para Zephyr: `src/` (código), `zephyr/` (`prj.conf` e `CMakeLists.txt`) e `platformio.ini`.

Ao ligar, deixe a placa **parada por 2 s** (calibração do offset, inclusive a gravidade em z).

## Capturar e plotar

```
pip install pyserial matplotlib
python python/leitor_serial.py COM3 dados_acelerometro.csv   # Ctrl+C para parar
python python/graficos.py dados_acelerometro.csv grafico.png
```

`python/simulacao.py` valida o algoritmo de integração com um movimento conhecido (dados simulados).
