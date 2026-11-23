# PREMARKET INTELLIGENCE — S&P 500

Sistema autónomo que, cada día con sesión regular en NYSE, investiga el contexto mundial
relevante para el S&P 500 y envía un informe HTML por Gmail antes de la apertura
(envío programado 08:59:15 ET = 06:59 CDMX en EDT / 07:59 CDMX en EST; en Gmail llega
antes de las 09:00 ET salvo retrasos de la plataforma).

## Arquitectura

```
Tarea programada en la nube de Claude (CRON_TZ=America/New_York, L–V 07:47)
  └─ sesión nueva ─ git clone de este repo ─ RUNBOOK.md
       ├─ pmi/calendar_nyse.py   festivos y cierres anticipados oficiales (NYSE 2026–2028)
       ├─ pmi/timing.py          reloj ET/CDMX, fases y límites (DST automático vía zoneinfo)
       ├─ pmi/econ_calendar.py   Forex Factory (feed JSON oficial) + datos reales verificados
       ├─ pmi/market_data.py     cierres oficiales FRED (10Y, 2Y, VIX, WTI, SPX)
       ├─ Claude: WebSearch/WebFetch → investigación, verificación y análisis en español
       ├─ pmi/news.py            reglas de fiabilidad, fusión de duplicados, orden por nivel
       ├─ pmi/render.py          HTML con estilos inline (Gmail) + texto plano
       ├─ pmi/mailer.py          envío por API de Resend a las 08:59:15 ET (Idempotency-Key)
       └─ Conector Gmail (solo lectura): reporte previo y control de duplicados
Tarea vigilante (L–V 09:12 ET): si no hay reporte de hoy en Gmail → correo de FALLO.
```

- No depende de tu computadora ni de una conversación abierta.
- Secretos solo en variables de entorno del entorno de Claude: `RESEND_API_KEY` y
  `PMI_RECIPIENT` (tu correo). Nada de eso está en el repo ni en los mensajes de las tareas.
- Remitente: `onboarding@resend.dev` (plan gratuito: solo puede enviar al correo con el
  que abriste la cuenta de Resend). Para otro remitente/destinatario: verificar un dominio.

## Operación

| Acción | Cómo |
|---|---|
| Ver ejecuciones | claude.ai → tareas programadas → cada ejecución es una sesión con su registro |
| Pausar | desactivar la tarea programada (o pedírselo a Claude) |
| Ejecutar ya | "ejecuta ahora la tarea PREMARKET" (dispara una ejecución fuera de horario) |
| Cambiar horario | editar `config.json → schedule` y la expresión cron de la tarea |
| Añadir fuentes/indicadores | `config.json → fred_series`, secciones 3–5 de RUNBOOK.md |
| Pruebas | `python -m pytest -q tests` |

## Mantenimiento

- **Cada diciembre:** añadir el año +2 a `pmi/calendar_nyse.py` desde
  https://www.nyse.com/markets/hours-calendars (el preflight sale con código 20 si la
  tabla se agota). Cierres extraordinarios: `EXTRAORDINARY`.
- Si Forex Factory cambia su feed, el reporte sale con "Calendario no disponible" y el
  registro lo indica; ajustar `sources.forexfactory_feed`.
- Gmail recorta correos > 102 KB: `build` compacta automáticamente las noticias
  moderadas/altas si hace falta.

## Límites conocidos (honestos)

- La hora de envío depende del arranque de la tarea programada (normalmente segundos o
  pocos minutos de variación). El vigilante alerta si no llega.
- Si faltan las variables de entorno, el reporte se genera pero no se puede enviar, y
  el vigilante tampoco puede alertar por correo (queda en el historial de la tarea).
- La primera vez, revisa que el correo de `onboarding@resend.dev` no caiga en Spam (si
  cae, márcalo como "No es spam" o crea un filtro en Gmail).
- Las cotizaciones de premarket solo aparecen si una fuente pública verificable muestra
  valor y hora; si no, se omiten. Los cierres FRED son del día hábil previo.
- Corte de información ~08:57 ET; lo material posterior al envío y antes de las 09:10
  puede salir como adenda de ÚLTIMA HORA.

## Costos

Ninguno adicional: plan gratuito de Resend (100 correos/día, 3,000/mes; se usan ~1–2
por día hábil), tu plan de Claude (tareas programadas y conectores) y fuentes públicas
gratuitas (FRED, Forex Factory, sitios oficiales). Cada ejecución consume uso de tu plan
de Claude.
