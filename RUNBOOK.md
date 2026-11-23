# RUNBOOK — Ejecución diaria de PREMARKET INTELLIGENCE — S&P 500

Este manual lo sigue Claude en cada ejecución programada (sesión nueva en la nube, sin
memoria de días anteriores). Léelo completo antes de empezar. El envío lo hace el código
(`pmi.cli send`, API de Resend) con las variables de entorno `RESEND_API_KEY` y
`PMI_RECIPIENT`, que configuró el usuario. Ni la clave ni el destinatario están en este
repositorio ni deben escribirse en ninguna llamada, archivo o mensaje.

**Principios:** precisión sobre especulación · calidad sobre cantidad · frescura · análisis
financiero, no titulares · fuentes verificables · puntualidad · nunca inventar.
No es un generador de señales de trading: contexto, riesgos y catalizadores.

---

## 0. Reloj (todas las horas son America/New_York)

| Hito | ET | Qué hacer |
|---|---|---|
| 07:47 | inicio | preflight, Forex Factory, FRED, contexto del reporte anterior |
| 07:50–08:30 | investigación amplia | noticias desde el cierre anterior (sección 3) |
| 08:31–08:45 | datos de 8:30 | capturar datos reales oficiales y sorpresas vs consenso |
| 08:45 | primera versión | escribir `work/report.json` y `build` (ya es enviable) |
| 08:50–08:57 | barrido final | últimas noticias/futuros; actualizar report.json y `build` |
| 08:57 | corte | `build` final y lanzar `send --at 08:59:15` (el código espera y envía) |
| 09:10 | límite duro | si aún no se envió, enviar YA lo que haya marcado como PARCIAL |

Consulta la fase con `python -m pmi.cli clock` entre bloques de trabajo. Si una fase se
agota, pasa a la siguiente aunque falte información: **la puntualidad manda**. Nunca
dejes que la investigación retrase el envío más allá de las 09:10 ET. Desde las 08:45
mantén siempre un `out/report.html` válido construido: si algo falla después, se envía
esa versión.

---

## 1. Preparación (≤ 3 min)

```bash
git clone --depth 1 https://github.com/elpza152678-blip/premarket-intelligence /tmp/pmi
cd /tmp/pmi
python -m pmi.cli preflight      # exit 0 = NYSE abre · 10 = cerrado · 20 = fuera de cobertura
```

- **Exit 10 (cerrado: fin de semana, festivo, cierre extraordinario):** termina sin enviar
  nada. Responde solo con una línea: "NYSE cerrado (motivo). Sin reporte."
- **Exit 20:** la tabla de festivos no cubre la fecha. Abre https://www.nyse.com/markets/hours-calendars
  con WebFetch; si hoy hay sesión regular continúa e incluye en `notes` que se debe
  actualizar `pmi/calendar_nyse.py`; si no, termina.
- **Cierre anticipado (13:00 ET):** sí hay reporte; el HTML lo marca solo.
- Si `env.RESEND_API_KEY` o `env.PMI_RECIPIENT` son false: no hay forma de enviar.
  Investiga igual, construye el reporte y termina explicando que faltan las variables
  (el vigilante no podrá alertar tampoco; el usuario lo verá en el historial de la tarea).
- Si en Gmail ya existe el reporte de hoy (paso 2), NO envíes otro. Termina informando.

Después, en paralelo:
```bash
python -m pmi.cli fred-fetch          # cierres oficiales Treasuries/VIX/WTI/SPX (no tiempo real)
python -m pmi.cli calendar-fetch      # feed oficial de Forex Factory (1 descarga; espera si hay rate-limit)
python -m pmi.cli calendar-show --usd-only
```
Si una fuente falla, sigue sin ella y anótala en `sources_failed`. Nunca rellenes con
valores supuestos.

## 2. Contexto del día anterior y control de duplicados (Gmail, solo lectura)

El conector de Gmail se usa únicamente para **leer** (nunca para enviar).
1. `search_threads` con `subject:"PREMARKET | S&P 500" newer_than:6d` (pageSize 5).
   Si hay uno con la fecha de HOY (sin "[PRUEBA]") → ya se envió: termina sin enviar.
   Además, Resend rechaza un segundo envío con la misma clave de idempotencia.
2. Abre el más reciente (`get_message`, PLAIN_TEXT) y toma la lista de títulos ya
   reportados. Regla: no presentes de nuevo una noticia vieja como nueva. Si hay un
   cambio sustancial, inclúyela con `status: "Actualizado"` y `update_note` explicando
   qué cambió. Si sigue siendo un catalizador vigente sin cambios, puede ir con
   `status: "Confirmado"` y aclaración breve ("vigente desde el …").

## 3. Investigación (07:50–08:30)

**Ventana:** desde el cierre de la sesión anterior (16:00 ET del día hábil previo que da
`preflight`; los lunes, desde el cierre del viernes, incluido el fin de semana) hasta el
corte. Incluye noticias anteriores solo si siguen siendo catalizadores materiales.

**Herramientas:** WebSearch (modo `standard`; `extended` solo para último minuto o temas
difíciles) y WebFetch para **abrir y verificar** cada noticia que vayas a publicar.
Lanza varias búsquedas en paralelo. Los sitios con paywall no se eluden: usa lo
visible, otra fuente u omite.

**Cobertura mínima (busca cada bloque por separado):**
- A. Fed/FOMC: decisiones, discursos de hoy, actas, expectativas de tasas (CME FedWatch
  citado por medios). BCE, BoJ, BoE, PBoC y otros con decisiones o sorpresas.
- B. Macro EE. UU.: datos de hoy y de ayer tras el cierre (CPI, PCE, PPI, NFP, claims,
  PIB, ISM/PMI, ventas minoristas, confianza), revisiones importantes, rendimientos.
- C. Empresas: resultados premarket/after-hours de ayer ("earnings before the bell
  today", "after hours movers"), guidance, megacaps (AAPL, MSFT, NVDA, AMZN, GOOGL, META,
  AVGO, TSLA, BRK, JPM…), semis/IA, bancos, energía, salud; M&A, litigios, reguladores.
- D. Política/geopolítica: aranceles, Casa Blanca/Congreso (presupuesto, deuda),
  sanciones, conflictos, China/Europa/Japón, petróleo y rutas comerciales.
- E. Mercados: futuros ES/NQ, VIX, 2Y/10Y, DXY, WTI/Brent, oro, Asia y Europa.
- F. Extraordinario: quiebras, crisis bancarias, ataques, fallos judiciales, ciberataques,
  apagones de infraestructura, cualquier catalizador nuevo no listado.

**Fuentes preferidas:** primarias (federalreserve.gov, bls.gov, bea.gov, dol.gov,
census.gov, treasury.gov, sec.gov/EDGAR, IR de empresas, bancos centrales) y medios de
referencia (Reuters, AP, Bloomberg, FT, WSJ, CNBC, MarketWatch).

**Reglas de verificación (obligatorias):**
1. Nada inventado: ni cifras, ni horas, ni titulares, ni enlaces, ni citas.
2. Cada noticia confirmada necesita ≥1 fuente con `verified: true`, lo que significa que
   **abriste la URL con WebFetch** y confirmaste que corresponde, con fecha (y hora si
   la hay). Si solo viste el snippet de búsqueda, `verified: false`.
3. Distingue hora del hecho y hora de publicación; zona horaria siempre explícita.
4. Noticia CRÍTICA de fuente no oficial: busca corroboración independiente (2.ª fuente).
5. Redes sociales = descubrimiento, no confirmación (salvo cuenta oficial verificable).
6. Hechos ≠ análisis/opinión. Si dos fuentes se contradicen, investiga; si no se
   resuelve, dilo en el resumen.
7. No atribuyas un movimiento del mercado a una noticia sin evidencia citada.
8. Información relevante pero no verificable → `unconfirmed` (o se omite).

**Relevancia:** incluye todo lo que supere un umbral razonable de impacto (puede ser 6
o 35 noticias). No rellenes. Niveles: CRÍTICO (puede mover materialmente el índice o
las expectativas), ALTO (índice, sectores grandes o sentimiento), MODERADO (seguimiento).

## 4. Datos de las 08:30 ET (08:31–08:40)

Para cada evento USD de las 08:30 en el calendario: abre la fuente oficial (BLS, BEA, DOL
— boletín semanal de claims —, Census). Si no carga, usa un medio de referencia que
publique la cifra (Reuters/AP/CNBC) y cítalo. Registra en `calendar_updates`:
`{"match": "Core PCE Price Index", "country": "USD", "actual": "0.3%", "source": "BEA",
"url": "...", "surprise": "+0.1 pp sobre consenso"}`. Sin dato verificado → no pongas
`actual` (saldrá "N/D"). Datos importantes también van como noticia CRÍTICA/ALTA con su
análisis. `calendar-show` muestra qué eventos ya pasaron y cuáles siguen PENDIENTES.
Eventos relevantes que el feed no trae (subastas del Tesoro, discursos Fed con hora
confirmada) van en `calendar_extra` con fuente.

## 5. `work/report.json` (esquema)

```json
{
  "date": "YYYY-MM-DD",
  "cutoff_et": "YYYY-MM-DDTHH:MM:SS-05:00",     // hora real de la última verificación
  "partial": false, "partial_reason": "",
  "sources_consulted_count": 0,
  "sources_failed": ["fuente (motivo)"],
  "notes": ["notas técnicas breves para el registro"],
  "executive_summary": {
    "overview": "3–5 frases; legible en < 2 min junto con las listas",
    "bullish": ["..."], "bearish": ["..."], "uncertain": ["..."]
  },
  "market": [   // SOLO con valor, instrumento, hora y fuente verificables
    {"label": "Futuros E-mini S&P 500 (contrato dic.)", "value": "6,912.25", "change": "+0.35%",
     "timestamp": "08:20 ET", "source": "CNBC", "url": "https://...", "note": "Futuros, no índice spot"}
  ],
  "news": [{
    "title": "Título breve en español",
    "level": "CRÍTICO|ALTO|MODERADO",
    "category": "Fed|Macro|Resultados|Geopolítica|Energía|Tecnología|...",
    "event_key": "clave-unica-del-hecho",          // misma clave = misma noticia (se fusiona)
    "urgency": 1,                                   // 1 = más urgente
    "summary": "40–90 palabras",
    "why_it_matters": "mecanismo: tasas, utilidades, valoración, liquidez, prima de riesgo…",
    "bias": "Alcista|Bajista|Mixto",
    "bias_detail": "argumentos alcistas y bajistas si los hay",
    "status": "Confirmado|Programado|Actualizado|No confirmado",
    "update_note": "qué cambió (si Actualizado)",
    "event_time": "24-nov-2026 07:00 ET", "published_time": "24-nov-2026 07:12 ET",
    "sources": [{"name": "Reuters", "url": "https://...", "published": "07:12 ET", "verified": true}],
    "confidence_fact": "Alta|Media|Limitada",
    "confidence_impact": "Alta|Media|Limitada"
  }],
  "unconfirmed": [ /* mismo formato; solo si es relevante */ ],
  "calendar_updates": [ /* sección 4 */ ],
  "calendar_extra": [{"time_et": "13:00", "country": "USD", "title": "Subasta Treasury 7Y",
                      "impact": "Medium", "source": "TreasuryDirect", "url": "https://..."}],
  "catalysts": [{"time": "10:00 ET", "title": "...", "detail": "qué podría cambiar el sentimiento"}],
  "conclusion": {"priced_in": "...", "could_change": "...", "volatility_focus": "...",
                 "open_uncertainties": "..."}
}
```
Sesgo = interpretación condicional, no predicción. Si el balance es contradictorio, dilo.
No fabriques probabilidades, correlaciones ni causalidades. La conclusión no da señales
de compra/venta.

Termómetro: ES/NQ, VIX, 10Y/2Y, DXY, WTI y Asia/Europa SOLO si una página que abriste
muestra el valor con su hora. No presentes datos retrasados como tiempo real (pon la hora
de la cotización). Los cierres oficiales de FRED se añaden solos como "Cierre previo".

## 6. Construir (08:45 y de nuevo al corte)

```bash
python -m pmi.cli build      # valida, fusiona duplicados, ordena, genera out/report.html y .txt
```
Revisa `warnings` y corrige lo importante (fuentes sin verificar, resúmenes fuera de
rango, falta de fecha o hora); vuelve a ejecutar `build`. Desde ese momento el reporte
ya puede enviarse.

## 7. Barrido final (08:50–08:57)

2–4 búsquedas rápidas: futuros de los últimos minutos, "breaking" mercados, comunicados
premarket y declaraciones de funcionarios. Incorpora en `work/report.json` lo material,
actualiza `cutoff_et` a la hora real de tu última verificación y ejecuta `build` otra vez.

## 8. Envío (programado a las 08:59:15 ET)

```bash
python -m pmi.cli send --backend resend --at 08:59:15
```
- El comando espera hasta la hora objetivo y envía HTML + texto plano. Si ya pasó la
  hora, envía de inmediato. Usa Idempotency-Key `pmi-<fecha>-report`: no puede duplicar.
- Éxito = salida con `"ok": true` y `provider_id` (Resend aceptó el correo). Exit 3 =
  fallo: lee `detail`; si es temporal (429/5xx) el comando ya reintentó; vuelve a lanzarlo
  una vez. 401/403 = clave inválida o destinatario no autorizado en Resend: no reintentes.
- La herramienta Bash corta a los 10 min: lanza `send --at` cuando falten menos de 9 min
  para las 08:59:15 (es decir, desde las 08:50:30).
- Si aparece algo material DESPUÉS del envío y antes de las 09:10, escribe
  `work/addendum.json` (`{"cutoff_et": "...", "note": "...", "news": [...]}`), ejecuta
  `python -m pmi.cli addendum` y envíala con
  `python -m pmi.cli send --backend resend --kind addendum`.
- Si a las 09:10 no se pudo enviar el completo, envía lo que haya con `"partial": true`
  y motivo (rebuild rápido).

## 9. Cierre de la sesión

Responde con 3–5 líneas: hora de inicio, hora de corte, hora de envío aceptado por Resend (ET y
CDMX), conteo de noticias, fuentes fallidas y advertencias. `python -m pmi.cli status`
muestra el registro. No hagas commits al repositorio desde la ejecución diaria.
