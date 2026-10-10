# Decisiones de diseño

Lo que se decidió al montar el proyecto, con el motivo. Si alguna de estas
decisiones se cambia, conviene anotar aquí por qué.

## 1. El backend corre en el local, no en la nube

El TPV habla por red local con un mini-PC del establecimiento. Un corte de
internet no impide cobrar, que es el riesgo real de un asador que factura casi
todo en dos horas al mediodía.

Consecuencia: la carta pública del QR y el panel de gestión no son accesibles
desde fuera mientras no se publique el mini-PC (túnel, VPN o una réplica en la
nube). Queda pendiente de decidir.

## 2. El IVA se agrupa por tipo, no se calcula línea a línea

Los precios de carta son **con IVA incluido**, así que la base se obtiene hacia
atrás: `base = redondeo(bruto / 1,10)`. El cálculo se hace **una sola vez por
tipo de IVA** sobre el bruto agregado del ticket, y la cuota se obtiene por
diferencia (`bruto - base`).

Así `base + cuota == total` siempre, por construcción. Calcularlo línea a línea
y sumar produce descuadres de un céntimo: con tres raciones de 0,95 €, la suma
por línea da 2,58 € de base y el cálculo agregado 2,59 €. Ese céntimo es la
causa habitual de rechazos cuando llegue VeriFactu.

Está en [`backend/app/core/money.py`](../backend/app/core/money.py) con un test
de control que fija el comportamiento.

## 3. El TPV todavía no funciona sin red

El modo offline completo (cola local de ventas y catálogo en el terminal) no
está hecho. Hoy, si el mini-PC o el wifi del local se caen, el TPV no cobra.

Al estar el servidor en el mismo local, el riesgo es mucho menor que con un
backend en la nube, pero no es cero: un router apagado deja el mostrador
parado. Antes de usarlo en producción hay que decidir entre:

- **Cola local en el terminal** (IndexedDB + reenvío idempotente). La API ya
  acepta el `id` generado por el TPV, así que reenviar una venta no la duplica;
  hay un test que lo comprueba. Falta la parte del cliente.
- **Aceptar el riesgo** y tener Dish o un talonario como respaldo los primeros
  meses.

La numeración de tickets la asigna el servidor, con una fila de contador
bloqueada por serie (`ticket_counters`). Si se implementa la cola local habrá
que decidir si el número se asigna en el terminal, y entonces cada terminal
necesita su propia serie.

## 4. Nada se borra

Un ticket cobrado es inmutable. Las correcciones se hacen con una venta de
signo contrario que apunta al original (`orders.refunds_order_id`), y el
original queda en estado `refunded` conservando sus importes. Las devoluciones
reciben su propio número de ticket.

Las variantes de producto se archivan en lugar de borrarse, y el nombre y el
precio se copian en la línea de venta (`name_snapshot`, `unit_price_cents`):
cambiar la tarifa hoy no altera el ticket de ayer. Hay un test que lo fija.

## 5. La media ración es una variante, no un producto

En Dish había 23 botones «MED …» duplicados. Aquí cada plato tiene variantes
(`Ración`, `Media`) y el botón abre un selector cuando hay más de una. En el
ticket la ración entera sale con el nombre limpio y la media como
«Alcachofas (Media)».

Los precios de media ración del `seed.py` son el 60 % de la ración redondeado a
múltiplos de 0,05 €. **Es una convención inventada**, no un dato del cliente:
hay que sustituirla por la exportación de Dish.

## 6. La fianza de paellera no es una venta

No lleva IVA y no entra en el ticket. Se registra en `deposits` y mueve caja a
través de `cash_movements`, de modo que el efectivo esperado del cierre Z
incluye las fianzas retenidas y descuenta las devueltas: el dinero está
físicamente en el cajón aunque no sea un ingreso.

**Pendiente de confirmar con la gestoría del cliente.**

## 7. El total de tarjeta del cierre Z no está conciliado

Sin integración con el datáfono, lo que el TPV llama «tarjeta» es lo que marcó
el cajero, no lo que liquidó el banco. El informe Z lo dice explícitamente con
el campo `card_reconciled: false` en lugar de presentarlo como cuadrado.

## 8. El freno de los PIN es por terminal, no por usuario

Bloquear al usuario tras cinco intentos fallidos dejaría el mostrador sin poder
cobrar por un PIN mal teclado en hora punta. El contador de intentos va por
terminal y vive en memoria del backend, que corre en el propio local.

Consecuencia: los PIN tienen que ser distintos entre sí, porque el cajero solo
teclea cuatro dígitos sin elegir usuario antes.

## 9. SQLite en desarrollo, PostgreSQL en producción

Los modelos usan tipos portables (`GUID`, `JSONType`) y Alembic genera las
migraciones en modo `batch`, que es el que entiende SQLite. Cambiar de motor es
cambiar `TPV_DATABASE_URL`.

Conviene pasar a PostgreSQL antes de la puesta en marcha: el bloqueo del
contador de tickets (`SELECT … FOR UPDATE`) solo es real en PostgreSQL. En
SQLite lo cubre la transacción de escritura, suficiente con un solo terminal.

## 10. VeriFactu queda fuera por ahora

El plazo es el 1/1/2027 para sociedades y el 1/7/2027 para autónomos. El modelo
de datos está preparado para encajarlo (numeración correlativa por serie sin
huecos, inmutabilidad de los tickets, desglose de IVA por tipos guardado en la
venta), pero no hay huella, ni QR, ni envío a la AEAT.

Cuando se aborde habrá que añadir a la factura los datos del software emisor
(nombre y NIF del productor, nombre, versión y número de instalación), que el
registro exige y hoy no existen en el modelo.

## 11. La caja de una venta la decide el servidor, no el terminal

El `session_id` venía en el cuerpo de la venta. El TPV nunca lo mandaba, así
que todas las ventas quedaban con `session_id` nulo y el cierre Z no contaba
ninguna: el efectivo esperado era el fondo inicial. Y cuando lo mandaba, podía
mandar el de una caja ya cerrada.

Ahora `POST /api/sales` resuelve la caja abierta en el servidor. Si el cliente
manda un `session_id`, se usa solo para comprobar que coincide; si no coincide,
409. Cobrar y devolver **exigen caja abierta**: el dinero que entra o sale del
cajón tiene que caer en algún cierre.

Consecuencia: el primer cobro del día falla si nadie ha abierto la caja. Es
deliberado, pero el TPV todavía no tiene pantalla de caja, así que hoy hay que
abrirla por API. **Es el siguiente hueco funcional a cerrar.**

## 12. El IVA del cierre Z se suma de los tickets, no se recalcula

El informe Z reagrupaba todas las líneas de la jornada y recalculaba la base
sobre el bruto agregado del día. Eso da un resultado distinto del que suman los
tickets emitidos: diez bolsas de 0,15 € al 21 % dan 0,30 € de cuota sumando los
tickets y 0,26 € reagrupando.

La decisión 2 justifica agregar **dentro de un ticket**, porque el ticket es el
documento. Agregar **entre tickets** rompe el cuadre contra los documentos
emitidos, que es lo que mira la gestoría y lo que exigirá VeriFactu. El Z suma
ahora el `vat_breakdown` ya guardado en cada venta.

## 13. Una devolución no se repite, y la parcial se distingue de la total

Se podía devolver el mismo ticket indefinidamente: tres llamadas devolvían el
triple de lo cobrado. Y una devolución parcial marcaba el original como
`refunded` entero, perdiendo la pista de lo que quedaba pendiente.

Ahora cada línea de devolución guarda de qué línea viene
(`order_lines.refunds_line_id`) y una línea ya devuelta se rechaza. El original
queda en `partially_refunded` mientras le quede algo sin devolver. Una
devolución no se devuelve.

La devolución se paga **por donde se cobró** (el método dominante del
original), no siempre en efectivo: devolver en metálico una comida que entró
por datáfono vaciaba el cajón.

## 14. El signo de un movimiento de caja lo pone el servidor

Era «positivo entra, negativo sale» por convención del cliente, sin nada que lo
ligara al tipo de movimiento: una retirada con importe positivo *subía* el
efectivo esperado, y el descuadre salía del doble de lo retirado. Ahora el
importe se manda en positivo y el signo se deriva del `kind`. `correction` es el
único con signo libre, y por eso exige motivo.

## 15. El freno del PIN cuenta por IP, nunca por un dato del cliente

La decisión 8 sigue en pie (por terminal, no por usuario), pero la clave del
contador era el `device_id` **que manda el cliente**: con un valor nuevo en cada
intento el freno no frenaba nada y se podían recorrer los 10.000 PIN de cuatro
dígitos. Ahora la clave es la IP del terminal y el `device_id` no entra en ella.

Un `ip|device_id` tampoco vale: basta con rotar la parte falsificable.

## 16. El día del negocio se corta en hora local

Los rangos de día se construían en UTC. Con Madrid en UTC+2, un ticket cerrado
a las 00:30 caía en la jornada anterior, y en Nochevieja el número de ticket
salía con el año anterior. Está en
[`backend/app/core/clock.py`](../backend/app/core/clock.py).

Nota de despliegue: `zoneinfo` no trae base de datos de zonas en Windows, así
que `tzdata` es una dependencia de producción, no un extra de desarrollo.

## 17. Lo archivado y lo agotado no se vende

Las variantes se archivan en lugar de borrarse (decisión 4), pero seguían
apareciendo en la botonera y se podían cobrar al precio viejo. Y `is_available`
(«agotado hoy») solo atenuaba el botón: la API cobraba igual.

Ahora el catálogo no sirve variantes archivadas, la carta pública no ofrece lo
agotado (en el TPV sí sigue, para que el cajero sepa que existe) y el cobro
rechaza ambos casos.

## 18. Lo que pasó a la base de datos, y por qué

Varias de estas reglas están además como restricción en la base, no solo en el
código: una sola caja abierta a la vez, número Z único, un plato del día por
fecha, número de ticket impreso único, CHECK en todas las columnas de estado,
coherencia entre el signo y el tipo de los movimientos, y que un ticket cobrado
tenga número.

El motivo: un estado desconocido se cae fuera de los filtros de los informes, y
entonces hay dinero cobrado que no aparece en ningún cierre. El código puede
tener un hueco; la restricción no. Están declaradas en los modelos **y** en la
migración, porque los tests construyen el esquema con `create_all` y si solo
vivieran en la migración la suite no las ejercería nunca.

En SQLite, además, la transacción abre con `BEGIN IMMEDIATE`: con el `BEGIN`
diferido de serie, dos cobros simultáneos no se serializaban sino que el
segundo moría con «database is locked» y el cajero se comía un 500.
