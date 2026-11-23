# Registro de pruebas — 23-nov-2026

Suite automática: `python -m pytest -q tests` → **36 pruebas OK**.

| Prueba | Resultado | Evidencia |
|---|---|---|
| A. Horario EDT/EST | OK | 9:00 ET = 14:00 UTC / 08:00 CDMX (EST) y 13:00 UTC / 07:00 CDMX (EDT); fases del reloj |
| B. NYSE cerrado | OK | Festivos 2026–2028 de nyse.com, idénticos a `exchange_calendars` (XNYS); fin de semana y festivo → exit 10; cierre anticipado → sí hay reporte |
| C. Noticias y fuentes | OK (en vivo) | Investigación real del 23-nov; noticias verificadas abriendo cada URL; sin enlace verificado → "no confirmada"; CRÍTICO de una sola fuente → aviso para corroborar (se añadió 2.ª fuente) |
| D. Duplicados | OK | Fusión por clave, URL o similitud. **Bug real encontrado y corregido:** un blog en vivo con una sola URL fusionaba 5 noticias distintas |
| E. Pendiente → publicado | OK | PENDIENTE antes de la hora; "PUBLICADO · real N/D" sin dato verificado (nunca se estima); PUBLICADO con dato oficial |
| F. HTML / Gmail | OK | Sin `<style>`/`<script>`/imágenes; enlaces http(s); 35 noticias con resúmenes largos ≈ 92 KB (< límite de recorte de Gmail de 102 KB) con compactación automática; **ajustes:** tabla de calendario rediseñada para móvil (390 px), espacios entre etiquetas conservados |
| G. Envío real | OK | 23-nov: correo `[PRUEBA]` vía Gmail (18:43 UTC) y, ya con Resend desde el entorno Default de la nube, alerta de prueba aceptada (HTTP 200) y entregada (status delivered) en Recibidos. Corregido: Resend rechazaba con 403 el agente de usuario genérico de Python |
| H. Nube sin tu computadora | OK | Ejecución en la nube: clonó el repo, preflight, Gmail (lectura) y envío por Resend con variables del entorno Default. Las tareas tipo chat no ven esas variables: las definitivas son las creadas desde Claude Code |
| I. Fallos | OK | Forex Factory caído → "Calendario no disponible"; clave inválida 401 → sin reintentos; 503 → reintento; programador tardío → envío inmediato; segundo envío → omitido |
| J. Cambios de horario | OK | 14-mar-2027: 07:47 ET pasa de 12:47 a 11:47 UTC (06:47 → 05:47 CDMX); 7-nov-2027 vuelve a EST |

## Hallazgos en vivo
- Forex Factory: la página HTML responde 403 a clientes automáticos; se usa su feed JSON oficial (`nfs.faireconomy.media`), que tiene límite de peticiones (se reintenta a los 75 s). El feed **no** trae el dato real: se toma de la fuente oficial.
- FRED bloquea agentes de usuario personalizados (se usa el estándar de Python). Los cierres de FRED pueden ir un día atrasados (se etiqueta la fecha).
- Un filtro de privacidad del entorno bloquea llamadas al conector de Gmail que combinan tu dirección con nombres propios. Por eso el envío diario usa Resend con variables de entorno.
