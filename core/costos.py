"""Estimación de tokens y costo ANTES de llamar a la IA externa (Anthropic/Claude).

Estándar transversal de los proyectos con API key: antes de ejecutar una tarea
contra un proveedor de pago hay que (1) contabilizar el volumen de datos, (2)
estimar los tokens y (3) traducirlo a dólares, para que el usuario confirme el
gasto. Tras la ejecución se registra el costo REAL (leído del `usage` que
devuelve el proveedor) y se compara contra lo estimado.

¡Quac! usa Anthropic (Claude), no OpenAI — por eso la tabla de precios y el
manejo del `usage` difieren de ReactivosFlow. Decisiones (estándar del usuario):
- Avisar y pedir confirmación antes de gastar.
- Módulo autónomo copiado a cada proyecto (sin dependencia compartida).
- Modelo no catalogado → estimar con el precio más caro conocido (cota superior).
- Registrar costo real post-lote desde `usage`.

Sobre el conteo de tokens: lo correcto para Claude es `client.messages.count_tokens`,
que NO gasta llamadas de generación. Pero para una estimación previa de un lote
grande (cientos de notas) eso serían cientos de llamadas de conteo. Aquí se usa
una heurística por caracteres —suficiente para decidir si ejecutar— y el costo
REAL se mide luego con el `usage`. NO usar tiktoken: es de OpenAI y subcuenta
los tokens de Claude ~15-20%.

Precios Claude (USD por 1M de tokens), verificados contra la skill claude-api
(cache 2026-06-04):
- claude-opus-4-8   : $5.00 in / $25.00 out
- claude-sonnet-4-6 : $3.00 in / $15.00 out
- claude-haiku-4-5  : $1.00 in / $5.00 out   (modelo por defecto del análisis de tono)
- claude-fable-5    : $10.00 in / $50.00 out
"""

from __future__ import annotations

from dataclasses import dataclass, field

PRECIOS_VERIFICADOS_EL = "2026-06-04"
CARACTERES_POR_TOKEN = 4.0


@dataclass(frozen=True)
class PrecioModelo:
    input_por_millon: float
    output_por_millon: float


# Claves normalizadas a la familia del modelo: el id real puede traer sufijo de
# fecha (p. ej. "claude-haiku-4-5-20251001"), así que el lookup empareja por
# prefijo de familia.
PRECIOS: dict[str, PrecioModelo] = {
    "claude-opus-4-8": PrecioModelo(5.00, 25.00),
    "claude-opus-4-7": PrecioModelo(5.00, 25.00),
    "claude-opus-4-6": PrecioModelo(5.00, 25.00),
    "claude-sonnet-4-6": PrecioModelo(3.00, 15.00),
    "claude-haiku-4-5": PrecioModelo(1.00, 5.00),
    "claude-fable-5": PrecioModelo(10.00, 50.00),
}


def _precio_de(modelo: str) -> tuple[PrecioModelo, bool]:
    """Devuelve (precio, es_catalogado). Empareja por prefijo de familia.

    Modelo no catalogado → precio más caro conocido (cota superior conservadora).
    """
    base = (modelo or "").strip().lower()
    # De la familia más larga a la más corta: si algún día se agrega una familia
    # que es prefijo de otra (p. ej. "claude-opus-4" junto a "claude-opus-4-8"),
    # el orden de inserción daría el precio equivocado en silencio.
    for familia in sorted(PRECIOS, key=len, reverse=True):
        if base == familia or base.startswith(familia):
            return PRECIOS[familia], True
    mas_caro = max(PRECIOS.values(), key=lambda p: p.output_por_millon)
    return mas_caro, False


def estimar_tokens(texto: str) -> int:
    if not texto:
        return 0
    return int(len(texto) / CARACTERES_POR_TOKEN) + 1


def _costo(tokens_in: int, tokens_out: int, precio: PrecioModelo) -> float:
    return (
        tokens_in / 1_000_000 * precio.input_por_millon
        + tokens_out / 1_000_000 * precio.output_por_millon
    )


@dataclass
class EstimacionCosto:
    modelo: str
    n_items: int
    tokens_input: int
    tokens_output: int
    costo_usd: float
    modelo_catalogado: bool
    precio_input_por_millon: float = 0.0
    precio_output_por_millon: float = 0.0
    notas: list[str] = field(default_factory=list)

    @property
    def tokens_totales(self) -> int:
        return self.tokens_input + self.tokens_output

    def resumen(self) -> str:
        lineas = [
            f"Modelo: {self.modelo}",
            f"Artículos a analizar: {self.n_items}",
            f"Tokens estimados de entrada:  {self.tokens_input:,}",
            f"Tokens estimados de salida:   {self.tokens_output:,}",
            f"Tokens totales (aprox.):      {self.tokens_totales:,}",
            "",
            f"COSTO ESTIMADO: ${self.costo_usd:,.4f} USD",
        ]
        if not self.modelo_catalogado:
            lineas.append("")
            lineas.append(
                "⚠ Modelo sin precio catalogado: estimado con el precio más alto "
                "conocido (cota superior). El costo real puede ser MENOR."
            )
        lineas.extend(self.notas)
        lineas.append("")
        lineas.append(
            f"(Precios Claude verificados el {PRECIOS_VERIFICADOS_EL}. Estimación aproximada; "
            "el costo real se mide del usage tras el lote.)"
        )
        return "\n".join(lineas)


def estimar_lote_tono(
    articulos: dict,
    modelo: str,
    prompt_overhead_chars: int = 900,
    fragmento_max_chars: int = 5000,
    tokens_salida_por_item: int = 512,
) -> EstimacionCosto:
    """Estima tokens y costo de analizar el tono de un corpus.

    Alineado con `sentiment_engine.analizar_tono`:
    - cada artículo envía hasta `fragmento_max_chars` del texto + el prompt fijo
      (`prompt_overhead_chars`: las ~900 instrucciones del _PROMPT);
    - la salida se acota por `max_tokens` (512). Es una cota superior: la
      respuesta real suele ser menor, así que el costo tiende a sobreestimar.

    `articulos` admite {id: texto} o {id: {"texto": ...}} (igual que el motor).
    """
    precio, catalogado = _precio_de(modelo)

    overhead_tokens = int(prompt_overhead_chars / CARACTERES_POR_TOKEN)
    tokens_input = 0
    n = 0
    for entrada in articulos.values():
        texto = entrada.get("texto", "") if isinstance(entrada, dict) else entrada
        fragmento = (texto or "")[:fragmento_max_chars]
        tokens_input += estimar_tokens(fragmento) + overhead_tokens
        n += 1

    tokens_output = tokens_salida_por_item * n
    costo = _costo(tokens_input, tokens_output, precio)

    notas: list[str] = []
    if n == 0:
        notas.append("No hay artículos cargados: nada que analizar.")

    return EstimacionCosto(
        modelo=modelo,
        n_items=n,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        costo_usd=costo,
        modelo_catalogado=catalogado,
        precio_input_por_millon=precio.input_por_millon,
        precio_output_por_millon=precio.output_por_millon,
        notas=notas,
    )


@dataclass
class CostoReal:
    modelo: str
    tokens_input: int
    tokens_output: int
    costo_usd: float
    modelo_catalogado: bool

    @property
    def tokens_totales(self) -> int:
        return self.tokens_input + self.tokens_output


def costo_real_desde_usages(modelo: str, usages: list) -> CostoReal:
    """Suma los `usage` de varias respuestas de Claude y calcula el costo real.

    Cada `usage` puede ser el objeto `message.usage` del SDK Anthropic o un dict.
    Se cuentan `input_tokens` + `cache_creation_input_tokens` (ambos a precio de
    entrada; Anthropic factura la escritura de caché ~1.25x, aquí se aproxima a
    1x — conservador hacia abajo, se documenta) y `output_tokens`. Las respuestas
    sin usage se ignoran sin romper el cálculo.
    """
    precio, catalogado = _precio_de(modelo)

    def _g(u, campo):
        if u is None:
            return 0
        if isinstance(u, dict):
            return int(u.get(campo, 0) or 0)
        return int(getattr(u, campo, 0) or 0)

    tokens_in = 0
    tokens_out = 0
    for u in usages:
        tokens_in += _g(u, "input_tokens") + _g(u, "cache_creation_input_tokens")
        # cache_read se factura ~0.1x; se omite del costo de entrada como
        # aproximación prudente (no infla el costo real reportado).
        tokens_out += _g(u, "output_tokens")

    return CostoReal(
        modelo=modelo,
        tokens_input=tokens_in,
        tokens_output=tokens_out,
        costo_usd=_costo(tokens_in, tokens_out, precio),
        modelo_catalogado=catalogado,
    )
