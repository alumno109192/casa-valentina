# TPV Casa Valentina

TPV, carta y encargos del Asador Casa Valentina. Sustituye a Dish POS.

- **Backend:** FastAPI + SQLAlchemy, corriendo en un mini-PC dentro del local.
- **Frontend:** workspace Angular con tres aplicaciones (`pos`, `admin`, `menu`)
  y una librería compartida.
- **TPV:** la app `pos` empaquetada con Capacitor para la Sunmi Android.

VeriFactu **no** está implementado todavía; ver [docs/decisiones.md](docs/decisiones.md).

## Estado actual

| Pieza | Estado |
|---|---|
| Modelo de datos y migraciones | Completo (17 tablas) |
| Cálculo de importes e IVA | Completo y con tests |
| API de ventas, caja y encargos | Completa (26 endpoints) |
| Catálogo inicial sembrado | 10 familias, 88 productos, **precios provisionales** |
| Pantalla de cobro del TPV | Funcional: botonera, variantes, efectivo, tarjeta, precio libre |
| Proyecto Android (Capacitor) | Generado y configurado en modo kiosko |
| Impresión en la Sunmi y cajón | **Pendiente** |
| Panel de gestión (`admin`) | Esqueleto vacío |
| Carta pública (`menu`) | Esqueleto vacío |
| Encargos en pantalla | API lista, interfaz pendiente |
| VeriFactu | Fuera del alcance actual |

## Arrancar en desarrollo

Backend:

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
cp .env.example .env
.venv/Scripts/alembic upgrade head
.venv/Scripts/python -m app.seed        # catálogo inicial, PIN del dueño 1234
.venv/Scripts/python -m uvicorn app.main:app --reload --host 0.0.0.0
```

La API queda en `http://localhost:8000`, con la documentación en `/docs`.

Frontend:

```bash
cd frontend
npm install
npm start               # TPV en http://localhost:4200
```

Tests del backend:

```bash
cd backend
.venv/Scripts/python -m pytest
```

## Compilar el APK del TPV

```bash
cd frontend
npm run build:pos       # compila con la URL de producción del mini-PC
npx cap sync android
cd android && ./gradlew assembleDebug
```

Requiere `JAVA_HOME` apuntando al JBR de Android Studio
(`C:\Program Files\Android\Android Studio\jbr`) y `local.properties` con la
ruta del SDK (`sdk.dir=C:/Users/<usuario>/AppData/Local/Android/Sdk`, con
barras normales: en un fichero de propiedades de Java las barras invertidas son
escapes).

El wrapper de Gradle está subido a 9.1.0 porque el JBR que trae Android Studio
es Java 25 y el Gradle 8.14 de la plantilla de Capacitor no lo soporta.

Antes de compilar para el local hay que poner la IP real del mini-PC en
[frontend/projects/pos/src/environments/environment.prod.ts](frontend/projects/pos/src/environments/environment.prod.ts)
y en el `network_security_config.xml` de Android.

## Estructura

```
backend/
  app/
    core/      dinero e IVA, configuración, BD, PIN y tokens
    models/    tablas SQLAlchemy
    schemas/   contratos Pydantic de la API
    services/  reglas de venta y numeración de tickets
    api/       routers (auth, catálogo, ventas, caja, encargos)
    seed.py    catálogo inicial
  alembic/     migraciones
  tests/       52 tests
frontend/
  projects/
    pos/       app del TPV (Capacitor Android)
    admin/     panel de gestión
    menu/      carta pública del QR
    shared/    tipos y cliente de API
  android/     proyecto Android generado
docs/
```

## Lo que falta antes de poder usarlo en el mostrador

1. **Precios reales.** Los del `seed.py` son inventados para poder probar.
   Hace falta la exportación de Dish.
2. **Impresión.** Sin ticket impreso el TPV no sirve en el mostrador. Hay que
   escribir el plugin de Capacitor contra el SDK de la Sunmi.
3. **Datos fiscales.** Razón social, NIF y forma jurídica están como
   «PENDIENTE» en la tabla `business`.
4. **Composición de los menús 1, 2 y 3.**
5. **Modo offline.** Hoy el TPV necesita el backend del local encendido; ver la
   decisión 3 en [docs/decisiones.md](docs/decisiones.md).
