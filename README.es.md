<h1 align="center">mxsat · Documentos del SAT para agentes de IA, con tus datos personales en tu computadora</h1>

<p align="center">
  <b>Lee facturas CFDI y acuses de declaración, prepara la siguiente factura con cifras exactas y verifica lo que
  se timbró. Tu RFC, los nombres y las direcciones se quedan en tu computadora.</b>
</p>

<p align="center">
  <a href="https://github.com/howware/mx-sat-documents/actions/workflows/ci.yml"><img src="https://github.com/howware/mx-sat-documents/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/versión-0.1.0-blue" alt="Versión 0.1.0">
  <a href="https://howware.org/es/"><img src="https://img.shields.io/badge/howware-adaptador-5a45d6" alt="adaptador howware"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/licencia-Apache%202.0-green" alt="Apache 2.0">
</p>

<p align="center"><a href="README.md">English</a> · <a href="docs/agent.md">Guía para agentes de IA</a></p>

> **Un adaptador de [howware](https://howware.org/es/).** Un howware es tu saber hacer puesto a trabajar con IA.
> Su núcleo (el protocolo y tus reglas) no sabe nada de archivos, portales ni bases de datos; los **adaptadores**
> lo conectan con ese entorno, como los puertos y adaptadores de la arquitectura limpia. `mxsat` es el adaptador
> de los documentos del SAT; lo usa el howware [facturacion](https://github.com/howware/facturacion). No tiene reglas fiscales: si un ingreso va a tasa 0 %, exento o con retenciones lo
> dicen las facturas que ya emitiste.

```text
mxsat cfdi read factura.xml          # una factura en JSON: montos, claves, impuestos; las personas como seudónimos
mxsat cfdi template factura.xml --name renta     # una plantilla privada a partir de una factura real
mxsat cfdi draft --template renta --total 5000 --ref <id del depósito>   # cifras exactas + ficha de captura
mxsat cfdi verify nueva.xml --draft renta-A152   # ¿el portal recibió exactamente lo aprobado?
mxsat acuse read acuse.pdf           # acuse de la declaración: periodo, montos, vencimiento
```

## Por qué

Facturar cada mes es copiar: llega un depósito al banco, y su monto, los datos del cliente, el concepto y el
periodo se escriben a mano en el portal del SAT. Un dígito equivocado, la forma de pago incorrecta o el periodo del
mes pasado son errores silenciosos que encuentra después tu contador, o el SAT.

`mxsat` hace la parte exacta. Un agente de IA hace la parte de criterio (qué depósito es de qué cliente, qué
facturar), siguiendo tus reglas.

## Qué hace

| Comando | Hace |
|---|---|
| `cfdi read` | Lee CFDI 3.3/4.0 timbrados: tipo, serie y folio, fechas, forma y método de pago, totales en centavos, conceptos con claves de producto y unidad, impuestos trasladados y retenidos, CFDI relacionados. Las partes, los lugares y las descripciones salen como seudónimos |
| `cfdi template` | Guarda una **plantilla privada** a partir de una factura real: receptor, concepto, impuestos, forma de pago, cuenta predial. Si la descripción nombra un mes (*del 1 al 31 de octubre de 2026*), aprende los marcadores y el desfase respecto a la fecha de emisión |
| `cfdi draft` | Aplica una plantilla a un monto: **a partir del depósito** (`--total`) encuentra el subtotal cuyos impuestos, redondeados a centavos como lo hace el portal, dan exactamente ese total. Llena el periodo (con el último día del mes), toma el folio siguiente, revisa un conjunto de reglas del CFDI 4.0 y escribe una **ficha de captura** en el orden del portal. Con `--ref`, un mismo depósito no se puede facturar dos veces |
| `cfdi verify` | Compara el XML timbrado contra la ficha aprobada, **campo por campo** (42 verificaciones en una factura de un concepto). Muestra las claves y montos que difieren; de los campos personales solo dice *difiere* |
| `cfdi templates` · `drafts` · `discard` | Lista plantillas y fichas; descarta una ficha pendiente |
| `acuse read` | Lee el PDF del acuse de recibo de la declaración: tipo, periodo, fecha de presentación, vencimiento, cada concepto con sus montos, total a pagar y vigencia de la línea de captura. Verifica el total contra los conceptos |

Cada comando imprime JSON en stdout; los errores también son JSON. Códigos de salida: `0` bien, `2` entrada
inválida, `3` error del almacén privado, `4` salida retenida por la revisión de privacidad.

## Privacidad

| Se queda en tu computadora | Lo que ve el agente |
|---|---|
| Los XML y PDF; el almacén privado (plantillas, fichas, fichas de captura) | Montos, fechas, claves del SAT, tasas, forma de pago, serie y folio |
| RFC, nombres, códigos postales, números fiscales extranjeros, descripciones, cuentas prediales, UUID, líneas de captura, números de operación | Seudónimos: `party_…`, `cfdi_…`, `place_…`; «present» para una línea de captura o un número fiscal extranjero |

Cómo funciona, y sus límites:
- **Los seudónimos son HMAC** de los valores reales con una llave que guardas en una variable de entorno
  (`MXSAT_KEY`). Con la llave son estables entre ejecuciones; sin ella cambian cada vez, y un aviso lo dice.
- **Falla cerrado.** Antes de imprimir, la salida se revisa contra cada valor personal de los documentos
  involucrados y contra formas de RFC, CURP y correo. Si encuentra algo, retiene la salida (código 4).
- **El almacén privado es JSON simple, sin cifrar.** Tiene su propio `.gitignore`. Mantenlo fuera del alcance de tu
  agente con una regla de denegación (ver la [guía para agentes](docs/agent.md)); `mxsat` no puede imponerlo solo.
- **Lo que ve el agente sale de tu computadora** hacia tu proveedor de IA, bajo sus términos: montos, fechas y el
  tipo de ingreso no se pueden ocultar, porque sin ellos no se puede conciliar nada.
- Lo que reciben el portal y el SAT cuando facturas está fuera de esta herramienta.

Todo el código es abierto, así que todo esto se puede revisar. Reporta los problemas de privacidad en privado
([SECURITY.md](SECURITY.md)).

## Instalación

```bash
uv tool install git+https://github.com/howware/mx-sat-documents
```

Define una llave de seudónimos una sola vez (cualquier texto largo y aleatorio; guarda una copia, como una
contraseña):

```powershell
[Environment]::SetEnvironmentVariable("MXSAT_KEY", "<texto largo aleatorio>", "User")   # Windows
```

```bash
export MXSAT_KEY="<texto largo aleatorio>"   # macOS / Linux, en el perfil de tu shell
```

El almacén va por omisión en `./mxsat-private`; cámbialo con `MXSAT_STORE` o `--store`.

## Límites

- **No timbra ni cancela.** Capturas la ficha en el portal del SAT (o con tu proveedor) y devuelves el XML timbrado
  para verificarlo. Timbrar a través de un proveedor autorizado (PAC) está planeado.
- Plantillas: facturas de ingreso, CFDI 4.0, MXN, un concepto con cantidad 1, sin facturas globales ni conceptos
  a cuenta de terceros. `read` acepta cualquier CFDI 3.3/4.0.
- Las reglas que revisa son un subconjunto de las del CFDI 4.0, no un validador completo; el SAT tiene la última
  palabra.
- `acuse read` está probado con el formato 2026 del acuse de la declaración provisional mensual.
- **No es asesoría fiscal** ni tiene relación con el SAT. Tu contador decide cómo tributa cada ingreso.

## Desarrollo

```bash
uv sync
uv run pytest -q                                    # solo documentos sintéticos
uvx ruff check src tests tools
git config core.hooksPath tools/git-hooks           # bloquea commits con documentos del SAT o datos personales
```

Reglas para personas y agentes que trabajan en este repositorio: [AGENTS.md](AGENTS.md).

## Licencia

[Apache 2.0](LICENSE).
