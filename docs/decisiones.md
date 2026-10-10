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
