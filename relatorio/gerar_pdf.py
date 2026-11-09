"""
Gera o relatorio PDF da atividade (codigo + graficos + comentarios).

Uso (na raiz do repositorio):
    pip install reportlab
    python relatorio/gerar_pdf.py --grafico grafico.png --repo https://github.com/USUARIO/REPO

--grafico : grafico gerado com os dados REAIS da placa (python/graficos.py).
            Se omitido, o PDF usa o grafico simulado e avisa isso.
"""
import argparse
import os
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANCH = "atividade-acelerometro-threads"

ap = argparse.ArgumentParser()
ap.add_argument("--grafico", default=None)
ap.add_argument("--repo", default="https://github.com/arturserejodantas7/acelerometro_threads")
ap.add_argument("--saida", default=os.path.join(RAIZ, "relatorio", "Relatorio_Acelerometro_Threads.pdf"))
args = ap.parse_args()

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping


def _registrar_fontes():
    """Fonte com suporte a ², Δ, →, ≈ (Helvetica padrao nao tem esses glifos)."""
    candidatos = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/ariali.ttf",
         "C:/Windows/Fonts/consola.ttf"),
        ("/Library/Fonts/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/System/Library/Fonts/Supplemental/Arial Italic.ttf", "/System/Library/Fonts/Supplemental/Courier New.ttf"),
    ]
    for reg, bold, ita, mono in candidatos:
        if all(os.path.exists(f) for f in (reg, bold, ita, mono)):
            pdfmetrics.registerFont(TTFont("Texto", reg))
            pdfmetrics.registerFont(TTFont("Texto-B", bold))
            pdfmetrics.registerFont(TTFont("Texto-I", ita))
            pdfmetrics.registerFont(TTFont("Mono", mono))
            addMapping("Texto", 0, 0, "Texto"); addMapping("Texto", 1, 0, "Texto-B")
            addMapping("Texto", 0, 1, "Texto-I"); addMapping("Texto", 1, 1, "Texto-B")
            return "Texto", "Texto-B", "Mono"
    return "Helvetica", "Helvetica-Bold", "Courier"


FONTE, FONTE_B, MONO = _registrar_fontes()
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName=FONTE_B, fontSize=15, spaceAfter=6, textColor=colors.HexColor("#1a3c6e"))
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName=FONTE_B, fontSize=12, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1a3c6e"))
P = ParagraphStyle("P", parent=ss["BodyText"], fontName=FONTE, fontSize=10, leading=14, alignment=TA_JUSTIFY)
LI = ParagraphStyle("LI", parent=P, leftIndent=12, bulletIndent=2)
CAP = ParagraphStyle("CAP", parent=P, fontSize=8.5, textColor=colors.HexColor("#555555"), alignment=1)
CODE = ParagraphStyle("CODE", fontName=MONO, fontSize=7, leading=8.6, backColor=colors.HexColor("#f5f6f8"),
                      borderPadding=4, leftIndent=2)

el = []


def p(t):
    el.append(Paragraph(t, P))


def li(itens):
    for t in itens:
        el.append(Paragraph(t, LI, bulletText="•"))


def codigo(caminho):
    with open(os.path.join(RAIZ, caminho), encoding="utf-8") as f:
        txt = f.read().replace("\t", "    ")
    el.append(Paragraph(f"<b>{caminho}</b>", ParagraphStyle("f", parent=P, fontSize=9, spaceBefore=6)))
    el.append(Preformatted(txt, CODE))


def figura(caminho, legenda, largura=16 * cm):
    from reportlab.lib.utils import ImageReader
    w, h = ImageReader(caminho).getSize()
    el.append(KeepTogether([Image(caminho, width=largura, height=largura * h / w), Paragraph(legenda, CAP)]))


# ---------------- Capa / identificacao ----------------
el.append(Paragraph("Atividade Acelerômetro – Serial com Threads", H1))
p("Microcontroladores 2 (PSI) – Escola Politécnica da USP<br/>"
  "Aluno: Artur Serejo Dantas – Nº USP 15441730<br/>"
  "Placa: FRDM-KL25Z · Sensor: MMA8451Q (I²C0, 0x1D) · RTOS: Zephyr")
el.append(Paragraph(f"Repositório: <link href='{args.repo}' color='blue'>{escape(args.repo)}</link> – branch <b>{BRANCH}</b>", ParagraphStyle("esq", parent=P, alignment=0)))

# ---------------- Arquitetura ----------------
el.append(Paragraph("1. Organização em threads", H2))
p("O projeto foi dividido em três threads com papéis independentes, ligadas por uma fila de mensagens "
  "(produtor–consumidor) e por um estado compartilhado protegido por mutex:")
tab = Table([
    ["Thread", "Prioridade", "Ativação", "Função"],
    ["t_aquisicao", "5 (maior)", "periódica 10 ms\n(k_timer)", "Lê os 6 bytes OUT_X..OUT_Z do MMA8451Q,\nconverte para m/s², tira o offset, envia à k_msgq"],
    ["t_integracao", "6", "por evento\n(k_msgq_get)", "Integra a → v → x a cada amostra\n(trapézio; Simpson 1/3 opcional)"],
    ["t_serial", "7 (menor)", "periódica 20 ms\n(k_sleep absoluto)", "Copia o estado sob mutex e envia\nt_ms;ax;ay;az;vx;vy;vz;px;py;pz"],
], colWidths=[2.5 * cm, 2.3 * cm, 3.1 * cm, 8.1 * cm])
tab.setStyle(TableStyle([
    ("FONT", (0, 0), (-1, -1), FONTE, 8.5), ("FONT", (0, 0), (-1, 0), FONTE_B, 8.5),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe6f1")), ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
el += [tab, Spacer(1, 6)]
p("O sensor é configurado em ±2 g (4096 contagens/g), ODR de 100 Hz e modo de baixo ruído (CTRL_REG1 = 0x1D). "
  "Nos primeiros 2 s a placa deve ficar parada: a média dessas 200 amostras é o offset de cada eixo "
  "(inclui a gravidade em z), que é subtraído das leituras seguintes.")

# ---------------- Escalonamento ----------------
el.append(Paragraph("2. Estratégia de escalonamento", H2))
li([
    "<b>Preemptivo por prioridade fixa.</b> No Zephyr as três threads são preemptivas (prioridade ≥ 0) e "
    "o escalonador sempre executa a thread pronta de maior prioridade (menor número). As prioridades são "
    "todas diferentes, então não foi necessário time-slicing (CONFIG_TIMESLICING=n).",
    "<b>Atribuição inspirada no Rate Monotonic.</b> A tarefa de menor período (aquisição, 10 ms) recebe a "
    "maior prioridade; a serial (20 ms) a menor. Além do período, pesou a criticidade: a integração supõe "
    "Δt constante, então o instante de amostragem precisa ter o menor jitter possível. Com prioridade "
    "máxima, quando o k_timer expira a aquisição preempta imediatamente qualquer outra thread.",
    "<b>Integração disparada por evento.</b> A t_integracao fica bloqueada em k_msgq_get e só roda quando "
    "chega uma amostra, logo após a aquisição voltar a dormir. Sua prioridade é maior que a da serial para que "
    "o cálculo nunca fique atrasado em relação aos dados. A fila de 16 posições absorve atrasos "
    "eventuais; a aquisição usa K_NO_WAIT para nunca bloquear e conta amostras perdidas.",
    "<b>Serial com a menor prioridade.</b> O printk de uma linha (~90 caracteres a 115200 bps) ocupa cerca de "
    "8 ms de UART, a tarefa mais longa do sistema. Se tivesse prioridade alta, atrasaria a amostragem; "
    "com prioridade baixa ela é simplesmente preemptada e retomada. Por isso também foi decimada para "
    "50 Hz (envia 1 de cada 2 estados), mantendo a ocupação da UART em ~40%. O período usa k_sleep com "
    "tempo absoluto (K_TIMEOUT_ABS_MS), para o tempo gasto no printk não se acumular.",
    "<b>Sincronização.</b> O estado (a, v, x) é compartilhado por um k_mutex, cuja herança de prioridade "
    "evita inversão de prioridade; a seção crítica é só a cópia de uma struct. Todas as threads bloqueiam "
    "(k_timer_status_sync, k_msgq_get, k_sleep) em vez de fazer espera ocupada, de modo que a CPU fica com "
    "a thread idle no tempo livre.",
    "<b>Utilização estimada.</b> Leitura I²C (~1 ms a cada 10 ms) ≈ 10%, integração em float por software "
    "(o KL25Z não tem FPU) ≈ 2%, serial (~8 ms a cada 20 ms) ≈ 40%: U ≈ 0,52, abaixo do limite de "
    "Liu &amp; Layland para 3 tarefas (≈ 0,78), portanto o conjunto é escalonável com folga.",
])

# ---------------- Integracao ----------------
el.append(Paragraph("3. Integração numérica", H2))
p("Foi usada a <b>regra dos trapézios</b>, aplicada duas vezes: v[n] = v[n−1] + Δt/2·(a[n−1] + a[n]) e "
  "x[n] = x[n−1] + Δt/2·(v[n−1] + v[n]), com Δt = 10 ms. Com INTEGRADOR_SIMPSON = 1 a velocidade passa a ser "
  "calculada pela <b>regra de Simpson 1/3</b> a cada par de intervalos: v[n] = v[n−2] + Δt/3·(a[n−2] + 4a[n−1] + a[n]). "
  "A quadratura gaussiana não foi usada porque exige avaliar a função em pontos internos não uniformes, e o "
  "sensor fornece amostras em instantes fixos e igualmente espaçados.")
p("A dupla integração amplifica qualquer offset residual (erro de posição cresce com t²). Para limitar a deriva: "
  "(i) calibração do offset na inicialização; (ii) zona morta de 0,05 m/s²; (iii) <i>zero-velocity update</i>: "
  "se os três eixos ficam abaixo de 0,10 m/s² por 500 ms, a velocidade é zerada.")
figura(os.path.join(RAIZ, "python", "validacao_integracao.png"),
       "Figura 1 – Validação do algoritmo (mesmas equações do firmware) com movimento conhecido de 0,30 m em x, "
       "ruído de 0,02 m/s² e offset residual. Dados simulados.", largura=14.5 * cm)
p("Na simulação, trapézio e Simpson ficam praticamente sobrepostos: a 100 Hz o erro de truncamento das duas "
  "regras é muito menor que o erro causado por ruído e offset. Sem zona morta/ZUPT, a posição deriva cerca de "
  "18 cm em 7 s; com as correções, o erro final cai para cerca de 6 cm e a posição para de derivar quando a placa para.")

# ---------------- Graficos ----------------
el.append(PageBreak())
el.append(Paragraph("4. Aceleração, velocidade e posição", H2))
if args.grafico:
    figura(args.grafico, "Figura 2 – Aceleração, velocidade e posição medidas com a FRDM-KL25Z "
                         "(capturadas com leitor_serial.py, plotadas com graficos.py).")
else:
    figura(os.path.join(RAIZ, "python", "grafico_simulacao.png"),
           "Figura 2 – Formato do gráfico gerado por graficos.py. ATENÇÃO: dados simulados; "
           "substituir pelo gráfico dos dados reais da placa.", largura=14.5 * cm)
p("Fluxo de captura: <font face='%s'>" % MONO + "python python/leitor_serial.py COM3 dados.csv</font> grava "
  "t, a, v e x em CSV; <font face='%s'>" % MONO + "python python/graficos.py dados.csv grafico.png</font> gera a figura.")

# ---------------- Codigo ----------------
el.append(PageBreak())
el.append(Paragraph("5. Código-fonte", H2))
for arq in ["src/main.c", "prj.conf", "CMakeLists.txt", "python/leitor_serial.py", "python/graficos.py"]:
    codigo(arq)


def rodape(c, d):
    c.saveState()
    c.setFont(FONTE, 7.5)
    c.setFillColor(colors.grey)
    c.drawString(2 * cm, 1.2 * cm, "Artur Serejo Dantas – Atividade Acelerômetro com Threads")
    c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"{d.page}")
    c.restoreState()


SimpleDocTemplate(args.saida, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                  bottomMargin=1.8 * cm, title="Atividade Acelerômetro – Threads",
                  author="Artur Serejo Dantas").build(el, onFirstPage=rodape, onLaterPages=rodape)
print("PDF gerado:", args.saida)
