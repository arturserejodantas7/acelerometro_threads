/*
 * Atividade Acelerometro - Serial (com threads)
 * Placa: FRDM-KL25Z  |  Sensor: MMA8451Q no I2C0 (endereco 0x1D)
 * RTOS: Zephyr
 *
 * Arquitetura (produtor -> consumidor):
 *
 *   [t_aquisicao]  prio 5, periodica 10 ms (100 Hz)
 *        |  le o MMA8451Q, converte para m/s^2, remove o offset
 *        v  k_msgq q_amostras
 *   [t_integracao] prio 6, liberada por evento (chegada de amostra)
 *        |  integra a -> v -> x (trapezio ou Simpson 1/3)
 *        v  estado compartilhado protegido por k_mutex
 *   [t_serial]     prio 7, periodica 20 ms (50 Hz)
 *           envia "t_ms;ax;ay;az;vx;vy;vz;px;py;pz" pela UART0 (OpenSDA)
 *
 * No Zephyr, numero de prioridade MENOR = prioridade MAIOR.
 * Todas sao threads preemptivas (prioridade >= 0).
 */

/* Compativel com o Zephyr do PlatformIO (2.7, includes sem "zephyr/")
 * e com versoes novas (3.x/4.x, includes com "zephyr/"). */
#if __has_include(<zephyr/kernel.h>)
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/i2c.h>
#include <zephyr/sys/printk.h>
#define MAIN_RETORNA_INT 1
#else
#include <kernel.h>
#include <device.h>
#include <drivers/i2c.h>
#include <sys/printk.h>
#define MAIN_RETORNA_INT 0
#endif

#define ABSF(x) ((x) < 0.0f ? -(x) : (x))
#include <string.h>

/* ------------------------------------------------------------------ */
/* Configuracao                                                        */
/* ------------------------------------------------------------------ */
#define MMA_ADDR            0x1D
#define MMA_REG_STATUS      0x00
#define MMA_REG_OUT_X_MSB   0x01
#define MMA_REG_WHO_AM_I    0x0D
#define MMA_REG_XYZ_CFG     0x0E
#define MMA_REG_CTRL1       0x2A
#define MMA_WHO_AM_I_VAL    0x1A

#define G_MS2               9.80665f
#define CONTAGENS_POR_G     4096.0f     /* faixa +-2 g, 14 bits */

#define PERIODO_AQ_MS       10          /* 100 Hz */
#define PERIODO_TX_MS       20          /* 50 Hz  */
#define DT_S                (PERIODO_AQ_MS / 1000.0f)

#define N_CALIBRACAO        200         /* 2 s parado para medir o offset */

/* Metodo de integracao: 0 = trapezio, 1 = Simpson 1/3 */
#define INTEGRADOR_SIMPSON  0

/* Reduz a deriva da dupla integracao */
#define ZONA_MORTA_MS2      0.05f       /* |a| menor que isso vira 0          */
#define LIMIAR_PARADO_MS2   0.10f       /* |a| < isso nos 3 eixos = "parado"  */
#define N_PARADO_ZERA_V     50          /* 500 ms parado -> zera velocidade   */

#define PRIO_AQ             5
#define PRIO_INT            6
#define PRIO_TX             7
#define PILHA_AQ            1024
#define PILHA_INT           1024
#define PILHA_TX            1536        /* printk com float usa mais pilha */

/* ------------------------------------------------------------------ */
/* Tipos e objetos do kernel                                           */
/* ------------------------------------------------------------------ */
struct amostra {
	uint32_t t_ms;
	float a[3];          /* m/s^2, ja sem offset */
};

struct estado {
	uint32_t t_ms;
	float a[3];
	float v[3];          /* m/s */
	float p[3];          /* m   */
};

K_MSGQ_DEFINE(q_amostras, sizeof(struct amostra), 16, 4);
K_MUTEX_DEFINE(mtx_estado);
K_SEM_DEFINE(sem_pronto, 0, 1);       /* libera integracao e serial apos calibrar */

static struct estado estado_global;
static const struct device *i2c_dev = DEVICE_DT_GET(DT_NODELABEL(i2c0));
static float offset[3];
static volatile uint32_t amostras_perdidas;

/* ------------------------------------------------------------------ */
/* Driver simples do MMA8451Q                                          */
/* ------------------------------------------------------------------ */
static int mma_init(void)
{
	uint8_t id;
	int ret;

	if (!device_is_ready(i2c_dev)) {
		printk("I2C0 nao esta pronto\n");
		return -ENODEV;
	}
	ret = i2c_reg_read_byte(i2c_dev, MMA_ADDR, MMA_REG_WHO_AM_I, &id);
	if (ret || id != MMA_WHO_AM_I_VAL) {
		printk("MMA8451Q nao encontrado (ret=%d id=0x%02x)\n", ret, id);
		return -EIO;
	}
	/* Standby para configurar */
	i2c_reg_write_byte(i2c_dev, MMA_ADDR, MMA_REG_CTRL1, 0x00);
	/* Faixa +-2 g */
	i2c_reg_write_byte(i2c_dev, MMA_ADDR, MMA_REG_XYZ_CFG, 0x00);
	/* ODR = 100 Hz (DR=011), LNOISE=1, ACTIVE=1 -> 0b0001_1101 */
	i2c_reg_write_byte(i2c_dev, MMA_ADDR, MMA_REG_CTRL1, 0x1D);
	return 0;
}

static int mma_ler(float a_ms2[3])
{
	uint8_t b[6];
	int ret = i2c_burst_read(i2c_dev, MMA_ADDR, MMA_REG_OUT_X_MSB, b, 6);

	if (ret) {
		return ret;
	}
	for (int i = 0; i < 3; i++) {
		int16_t bruto = (int16_t)((b[2 * i] << 8) | b[2 * i + 1]) >> 2; /* 14 bits */
		a_ms2[i] = (bruto / CONTAGENS_POR_G) * G_MS2;
	}
	return 0;
}

/* ------------------------------------------------------------------ */
/* Thread 1: aquisicao (periodica, maior prioridade)                   */
/* ------------------------------------------------------------------ */
static void t_aquisicao(void *p1, void *p2, void *p3)
{
	struct k_timer tmr;
	struct amostra s;
	float a[3], soma[3] = {0};

	if (mma_init() != 0) {
		return;
	}

	k_timer_init(&tmr, NULL, NULL);
	k_timer_start(&tmr, K_MSEC(PERIODO_AQ_MS), K_MSEC(PERIODO_AQ_MS));

	/* Calibracao: placa parada sobre a mesa.
	 * O offset inclui a gravidade em z (aprox. +1 g). */
	printk("# Calibrando, mantenha a placa parada...\n");
	for (int n = 0; n < N_CALIBRACAO; n++) {
		k_timer_status_sync(&tmr);
		if (mma_ler(a) == 0) {
			for (int i = 0; i < 3; i++) {
				soma[i] += a[i];
			}
		}
	}
	for (int i = 0; i < 3; i++) {
		offset[i] = soma[i] / N_CALIBRACAO;
	}
	printk("# Offset: %.3f %.3f %.3f m/s2\n",
	       (double)offset[0], (double)offset[1], (double)offset[2]);
	k_sem_give(&sem_pronto);

	while (1) {
		/* Bloqueia ate o proximo periodo: libera a CPU para as outras threads */
		k_timer_status_sync(&tmr);

		if (mma_ler(a) != 0) {
			continue;
		}
		s.t_ms = k_uptime_get_32();
		for (int i = 0; i < 3; i++) {
			s.a[i] = a[i] - offset[i];
		}
		/* K_NO_WAIT: a thread de tempo real nunca bloqueia esperando o consumidor */
		if (k_msgq_put(&q_amostras, &s, K_NO_WAIT) != 0) {
			amostras_perdidas++;
		}
	}
}

/* ------------------------------------------------------------------ */
/* Thread 2: integracao numerica (liberada por evento)                 */
/* ------------------------------------------------------------------ */
static void t_integracao(void *p1, void *p2, void *p3)
{
	struct amostra s;
	float a0[3] = {0}, a1[3] = {0};   /* a[n-2], a[n-1] */
	float v0[3] = {0}, v1[3] = {0};   /* v[n-2], v[n-1] */
	(void)a0; (void)v0;               /* so usados no modo Simpson */
	float v[3] = {0}, p[3] = {0};
	int parado = 0;
	uint32_t n = 0;

	k_sem_take(&sem_pronto, K_FOREVER);
	k_sem_give(&sem_pronto);              /* repassa para a thread serial */

	while (1) {
		k_msgq_get(&q_amostras, &s, K_FOREVER);

		/* Zona morta: elimina ruido residual em torno de zero */
		bool quieto = true;
		for (int i = 0; i < 3; i++) {
			if (ABSF(s.a[i]) >= LIMIAR_PARADO_MS2) {
				quieto = false;
			}
			if (ABSF(s.a[i]) < ZONA_MORTA_MS2) {
				s.a[i] = 0.0f;
			}
		}

		if (n == 0) {
			/* primeira amostra: so guarda */
		} else {
			for (int i = 0; i < 3; i++) {
				float vn;
#if INTEGRADOR_SIMPSON
				if ((n % 2) == 0) {
					/* Simpson 1/3 sobre os 2 ultimos intervalos:
					 * v[n] = v[n-2] + dt/3 (a[n-2] + 4 a[n-1] + a[n]) */
					vn = v0[i] + (DT_S / 3.0f) * (a0[i] + 4.0f * a1[i] + s.a[i]);
				} else {
					/* amostra impar: trapezio no intervalo isolado */
					vn = v1[i] + 0.5f * DT_S * (a1[i] + s.a[i]);
				}
#else
				/* Regra dos trapezios: v[n] = v[n-1] + dt/2 (a[n-1] + a[n]) */
				vn = v1[i] + 0.5f * DT_S * (a1[i] + s.a[i]);
#endif
				/* posicao: trapezio sobre a velocidade */
				p[i] += 0.5f * DT_S * (v1[i] + vn);
				v[i] = vn;
			}
		}

		/* "Zero-velocity update": parado por um tempo -> v = 0 */
		parado = quieto ? parado + 1 : 0;
		if (parado >= N_PARADO_ZERA_V) {
			for (int i = 0; i < 3; i++) {
				v[i] = 0.0f;
			}
		}

		for (int i = 0; i < 3; i++) {
			a0[i] = a1[i];
			a1[i] = s.a[i];
			v0[i] = v1[i];
			v1[i] = v[i];
		}
		n++;

		k_mutex_lock(&mtx_estado, K_FOREVER);
		estado_global.t_ms = s.t_ms;
		memcpy(estado_global.a, s.a, sizeof(s.a));
		memcpy(estado_global.v, v, sizeof(v));
		memcpy(estado_global.p, p, sizeof(p));
		k_mutex_unlock(&mtx_estado);
	}
}

/* ------------------------------------------------------------------ */
/* Thread 3: envio pela serial (periodica, menor prioridade)           */
/* ------------------------------------------------------------------ */
static void t_serial(void *p1, void *p2, void *p3)
{
	struct estado e;
	uint32_t ultimo_t = 0;
	int64_t prox;

	k_sem_take(&sem_pronto, K_FOREVER);
	printk("t_ms;ax;ay;az;vx;vy;vz;px;py;pz\n");

	prox = k_uptime_get();
	while (1) {
		prox += PERIODO_TX_MS;
		/* Espera absoluta: o periodo nao acumula o tempo gasto no printk */
		k_sleep(K_TIMEOUT_ABS_MS(prox));

		k_mutex_lock(&mtx_estado, K_FOREVER);
		e = estado_global;              /* copia rapida, solta o mutex logo */
		k_mutex_unlock(&mtx_estado);

		if (e.t_ms == ultimo_t) {
			continue;                   /* nada novo */
		}
		ultimo_t = e.t_ms;

		printk("%u;%.3f;%.3f;%.3f;%.4f;%.4f;%.4f;%.4f;%.4f;%.4f\n",
		       e.t_ms,
		       (double)e.a[0], (double)e.a[1], (double)e.a[2],
		       (double)e.v[0], (double)e.v[1], (double)e.v[2],
		       (double)e.p[0], (double)e.p[1], (double)e.p[2]);
	}
}

K_THREAD_DEFINE(id_aq,  PILHA_AQ,  t_aquisicao,  NULL, NULL, NULL, PRIO_AQ,  0, 0);
K_THREAD_DEFINE(id_int, PILHA_INT, t_integracao, NULL, NULL, NULL, PRIO_INT, 0, 0);
K_THREAD_DEFINE(id_tx,  PILHA_TX,  t_serial,     NULL, NULL, NULL, PRIO_TX,  0, 0);

/* Toda a aplicacao roda nas threads acima; main pode terminar. */
#if MAIN_RETORNA_INT
int main(void)
{
	return 0;
}
#else
void main(void)
{
}
#endif
