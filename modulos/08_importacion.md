# SESIÓN 08 — Importación desde Excel
# [CLAUDE.md se carga automáticamente — no hace falta incluirlo]

## PREREQUISITOS
- Sesiones 01 a 07 completadas y funcionando
- Services de proveedores (03), categorías y productos (04), stock (05) y
  clientes (06) ya implementados
- `core/excel.py::leer_tabla` (creado en la sesión 03 para la importación del
  dólar)

## OBJETIVO DE ESTA SESIÓN
Carga inicial de datos de un cliente nuevo desde Excel: **proveedores,
clientes y productos**. Es la herramienta para poner en marcha una instancia
sin cargar miles de registros a mano.

## CONTEXTO DE NEGOCIO
- **Solo altas.** La importación nunca modifica registros existentes: si una
  fila choca con algo que ya existe, es un error de esa fila. (Los cambios
  masivos de precio ya se resuelven con el dólar por proveedor.)
- **Todo o nada**, igual que el Excel del dólar: si alguna fila tiene error no
  se aplica ninguna.
- Primero se **valida** (vista previa sin tocar la base) y después se
  **importa** el mismo archivo. El servidor no guarda el archivo entre los dos
  pasos: `importar` vuelve a validar todo desde cero.
- Orden sugerido: proveedores → productos (los productos referencian
  proveedores por nombre). Clientes es independiente.

---

## MODELO DE DATOS

No hay tablas nuevas. Cada alta pasa por el service del módulo dueño
(`crear_proveedor`, `crear_cliente`, `crear_categoria`, `crear_producto`,
`registrar_ingreso`, `definir_minimo`), así que se aplican **exactamente las
mismas validaciones y la misma auditoría** que el alta manual (Principio 2: no
se duplica ninguna regla en la importación).

Permiso: módulo `IMPORTACION`, acción `crear` (sesión 02; por defecto solo
Admin).

---

## BACKEND

### `/app/core/excel.py` (ya existe desde la sesión 03; se generaliza si hace falta)
- `leer_tabla(contenido, columnas_requeridas, columnas_opcionales)`: abre el
  `.xlsx` con openpyxl (`read_only`, `data_only`), toma la primera hoja, ubica
  las columnas por nombre de encabezado (sin importar orden, mayúsculas ni
  tildes; ignora columnas extra), saltea filas totalmente vacías y devuelve
  `[(numero_de_fila, {columna: valor})]`. Archivo no-xlsx, vacío o sin alguna
  columna requerida → `ReglaDeNegocio` (409).
- `generar_plantilla(hoja, columnas, instrucciones, filas=None)`: libro con la
  hoja de datos (encabezados en negrita, anchos ajustados y, si se pasan,
  filas precargadas — lo usa la plantilla del dólar) y una hoja
  "Instrucciones" (columna, obligatoria, formato, valores posibles, ejemplo).
- Límites: 5 MB y 5.000 filas por archivo (409 "El archivo supera …").

### `/app/services/importacion.py`
Un **motor único** parametrizado por una definición por tipo
(`DEFINICIONES = {"proveedores": …, "clientes": …, "productos": …}`): columnas,
parser/validador por columna y función de alta. Nada de lógica copiada entre
tipos.

- `validar(tipo, contenido) -> ResultadoImportacion` y
  `importar(tipo, contenido, autor, ip) -> ResultadoImportacion`, ambos sobre
  `_procesar(tipo, contenido, aplicar)`:
  1. `leer_tabla`.
  2. Parsea cada celda (texto normalizado con `normalizar_texto`, números con
     coma o punto decimal, enums por etiqueta legible o valor).
  3. Detecta duplicados **dentro del archivo** (misma clave en dos filas).
  4. Ejecuta las altas dentro de un **SAVEPOINT** general, con cada fila en
     su propio savepoint anidado (un error de base en una fila no rompe la
     sesión), llamando a los services
     reales; cada `ReglaDeNegocio`/`ValidationError`/`IntegrityError` se convierte en
     `{fila, columna, error}` y se sigue con la fila siguiente (para reportar
     todos los errores de una vez).
  5. Si hay errores **o** `aplicar=False` → rollback del savepoint.
     Si `aplicar=True` y no hay errores → se confirma y se audita
     `importacion.<tipo>` con `{archivo, filas, creados}`.
  Validar y aplicar usan el mismo camino, así la vista previa nunca promete
  algo que la importación después rechaza.
- `ResultadoImportacion`: `{tipo, filas_leidas, filas_validas, creados,
  categorias_nuevas: [camino], errores: [{fila, columna | null, error}],
  aplicado: bool}`.

#### Columnas por tipo (`*` = obligatoria)

**Proveedores** — `nombre*`, `moneda*` ("Pesos"/"Dólares" o `ars`/`usd`),
`dolar_actual` (obligatorio y > 0 si es en dólares; ignorado si es en pesos),
`pais`, `provincia`, `telefono`, `email`, `notas`.
Error si ya existe un proveedor con el mismo nombre (sin tildes ni
mayúsculas) o si el nombre se repite en el archivo.

**Clientes** — `nombre*`, `dni`, `cuit`, `condicion_iva` (etiqueta o valor;
default Consumidor final), `domicilio`, `codigo_postal`, `localidad`,
`telefono`, `email`. DNI y CUIT únicos en la base y en el archivo; CUIT con
dígito verificador válido; CUIT obligatorio si no es consumidor final
(mismas reglas de `crear_cliente`).

**Productos** — `descripcion*`, `categoria*`, `proveedor*`, `costo*`,
`margen` (default `margen_default`), `sku_proveedor`, `descuento_producto`,
`peso_gramos`, `temporada` ("Atemporal"/"Otoño-Invierno"/"Primavera-Verano"
o su valor), `ubicacion_deposito`, `stock_inicial` (entero ≥ 0),
`stock_minimo` (entero ≥ 0).
- `categoria`: camino separado por `>` ("Ropa > Remeras > Lisas"), hasta 5
  niveles. Cada nivel se busca entre los hermanos sin tildes ni mayúsculas y,
  si no existe, **se crea** (`crear_categoria`; se informa en
  `categorias_nuevas`). La categoría final no puede tener subcategorías
  ("La categoría '…' tiene subcategorías: indicá el camino hasta el último
  nivel.").
- `proveedor`: nombre exacto sin tildes ni mayúsculas; tiene que existir y
  estar activo (incluye los importados antes en otro archivo, no en el mismo).
- Resto: mismas validaciones de `crear_producto` (descripción única por
  categoría y proveedor, costo > 0, descuento ≤ `descuento_maximo`, etc.).
  `stock_infinito` no se importa (lo define el Admin a mano).
- `stock_inicial` > 0 → ingreso de proveedor con nota "Importación inicial";
  `stock_minimo` → `definir_minimo`.

### Endpoints (`/api/v1/importacion`)
```
GET   /{tipo}/plantilla   → descarga importar-<tipo>-YYYY-MM-DD.xlsx          [IMPORTACION crear]
POST  /{tipo}/validar     → multipart `archivo` → ResultadoImportacion (aplicado=false)  [IMPORTACION crear]
POST  /{tipo}/importar    → multipart `archivo` → ResultadoImportacion        [IMPORTACION crear]
```
`tipo` ∈ `proveedores | clientes | productos` (Enum de path; otro valor → 422).
Status 200 aunque haya errores de filas (van en `errores`); errores de archivo
→ 409.

---

## FRONTEND

Tarjeta **"Importar desde Excel"** en el hub Configuraciones (sesión 03;
visible con `IMPORTACION crear`).

### `/importacion` (`pages/importacion/index.html` + `static/js/importacion.js`)
- Encabezado "Importar desde Excel" con volver a "Configuraciones".
- Texto: "Cargá los datos iniciales en tres pasos: descargá la plantilla,
  completala y subila. Primero proveedores, después productos."
- Selector de tipo en pestañas: **Proveedores / Clientes / Productos**.
- Para el tipo elegido:
  1. Botón **"Descargar plantilla"**.
  2. Zona para subir el `.xlsx` (arrastrar o elegir).
  3. Botón **"Validar"** → resumen: "N filas leídas · M listas para importar",
     y para productos "Se van a crear K categorías nuevas" (lista
     desplegable con los caminos). Si hay errores: tabla "Errores (no se va a
     importar nada hasta corregirlos)" Fila | Columna | Error, paginada de a 10.
  4. Botón **"Importar"**, habilitado solo si la validación dio 0 errores y
     el archivo no cambió; pide confirmación (`modal_confirmacion`: "Se van a
     crear M <tipo>. Esta acción no se deshace desde el sistema.").
  5. Resultado: toast de éxito con la cantidad creada y link al listado
     correspondiente.
- Todo el trabajo lo hace el backend; el frontend no lee el Excel.

---

## TESTS (`tests/test_importacion.py`)
- Plantilla descargada y vuelta a subir vacía → 409 por no tener filas;
  con filas válidas → importa.
- Columnas en otro orden y columnas extra → funciona.
- Proveedor en dólares sin dólar → error de fila; proveedor duplicado en base
  y en archivo → error.
- Cliente con CUIT inválido o DNI repetido → error.
- Producto: crea categorías faltantes del camino; rechaza categoría con
  subcategorías; proveedor inexistente o inactivo → error; precio de venta
  igual al del alta manual; `stock_inicial` genera el movimiento de ingreso.
- Todo o nada: un archivo con 1 fila mala no crea nada (ni categorías).
- `validar` no deja rastros en la base (ni auditoría).
- Sin `IMPORTACION crear` → 403.

---

## CRITERIOS DE ACEPTACIÓN
- Proveedores, clientes y productos se importan desde su plantilla con las
  mismas reglas que el alta manual (la importación no tiene validaciones
  propias duplicadas).
- Solo altas; nunca modifica registros existentes.
- Validar muestra todos los errores de una vez (fila y columna) sin tocar la
  base; importar es todo o nada.
- Las categorías faltantes se crean a partir del camino y se informan antes
  de importar.
- La importación queda en la auditoría con el archivo y la cantidad creada.
