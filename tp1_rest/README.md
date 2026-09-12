# Mini-TP 1 — API REST con FastAPI

API que sirve el modelo de arrestos de Chicago por HTTP. Carga `model/model.pkl` **una sola vez** al arrancar, recibe los 6 campos crudos de un reporte, hace la codificación en el servidor y devuelve la predicción.

← [README general del repo](../README.md)

## Cómo correrlo

Todos los comandos se corren desde la raíz del repo.

| comando | qué hace |
|---|---|
| `make rest-run` | levanta la API local con uvicorn en el puerto 8000 (docs interactivas en `/docs`) |
| `make rest-up` | construye la imagen, levanta el contenedor y espera a que responda `/health` |
| `make rest-health` | consulta `GET /health` |
| `make rest-client` | corre el cliente de prueba (`client.py`) contra la API |
| `make rest-logs` | muestra los logs del contenedor |
| `make rest-down` | detiene el contenedor |

Los targets llevan el prefijo `rest-` porque el repo sirve el mismo modelo por varios protocolos; `make help` los lista todos.

Sin `make`:

```bash
uv run uvicorn tp1_rest.app:app --port 8000          # local
docker build -f tp1_rest/Dockerfile -t arrest-rest . # imagen
docker run --rm -p 8000:8000 arrest-rest             # contenedor
uv run python tp1_rest/client.py                     # cliente de prueba
```

## Endpoints

| endpoint | respuesta |
|---|---|
| `GET /health` | 200 `{"status": "ok", "model_name": "chicago-arrest-xgboost", "model_version": 1}`; 503 si no se pudo cargar `model/model.pkl` |
| `POST /v1/predict` | recibe los 6 campos crudos y devuelve `{"arrest", "probability", "model_name", "model_version"}`; 422 si el payload no cumple el contrato; 503 si no hay modelo |
| `POST /v1/predict/batch` | recibe `{"reports": [...]}` con 1 a 1000 reportes y devuelve `{"predictions": [...]}` en el mismo orden; 422 si el lote está vacío, pasa de 1000 o algún reporte no cumple; 503 si no hay modelo |
| `GET /v1/metadata` | describe el modelo cargado: `name`, `version`, `framework`, `inputs` (los 6 campos crudos), `features` (las 7 del modelo), `metrics` y `trained_at`; 503 si no hay modelo |

Los endpoints de negocio van bajo el prefijo `/v1`; `/health` queda afuera porque es de infraestructura.

## Ejemplo

El payload de abajo es la primera fila de `Crimes_Chicago_2024.csv`. Es el `EXAMPLE_REPORT` de `arrest_model/schemas.py`: el mismo que usan la doc de OpenAPI, el cliente y los tests, así no se desincronizan. La respuesta está fijada como valor de referencia en `tests/test_api.py`.

```bash
curl -X POST http://127.0.0.1:8000/v1/predict -H "Content-Type: application/json" -d '{
  "iucr": "1310", "primary_type": "CRIMINAL DAMAGE", "location_description": "APARTMENT",
  "date": "2024-12-31T23:58:00", "latitude": 41.771470188, "longitude": -87.59074212
}'
```

```json
{"arrest": 0, "probability": 0.06843266636133194, "model_name": "chicago-arrest-xgboost", "model_version": 1}
```

Un lote devuelve las predicciones en el mismo orden en que se mandaron los reportes:

```bash
curl -X POST http://127.0.0.1:8000/v1/predict/batch -H "Content-Type: application/json" -d '{"reports":[
 {"iucr":"1310","primary_type":"CRIMINAL DAMAGE","location_description":"APARTMENT","date":"2024-12-31T23:58:00","latitude":41.771470188,"longitude":-87.59074212},
 {"iucr":"0820","primary_type":"THEFT","location_description":"STREET","date":"2024-07-04T12:00:00","latitude":41.88,"longitude":-87.63}]}'
```

```json
{"predictions": [
  {"arrest": 0, "probability": 0.06843266636133194, "model_name": "chicago-arrest-xgboost", "model_version": 1},
  {"arrest": 0, "probability": 0.022384578362107277, "model_name": "chicago-arrest-xgboost", "model_version": 1}
]}
```

Y `GET /v1/metadata` describe qué modelo está sirviendo:

```json
{
  "name": "chicago-arrest-xgboost", "version": 1, "framework": "xgboost 3.4.1",
  "inputs": ["iucr", "primary_type", "location_description", "date", "latitude", "longitude"],
  "features": ["IUCR_freq", "Primary_Type_freq", "Location_Description_freq", "Day_sin",
               "X Coordinate_standardized", "Y Coordinate_standardized",
               "Distance Crime To Police Station_standardized"],
  "metrics": {"accuracy": 0.9119107677755005, "precision": 0.9047016906479248,
              "recall": 0.9119107677755005, "f1": 0.9039410418577858,
              "auc": 0.8861377061145108, "mcc": 0.5811392832702954},
  "trained_at": "2026-09-11T19:13:30Z"
}
```

## Qué valida el contrato

El payload se valida **antes** de llegar al modelo; si no cumple, la API responde 422 con el detalle del campo.

| campo | regla |
|---|---|
| `iucr` | texto de 4 caracteres: 3 dígitos y un dígito o letra (`^[0-9]{3}[0-9A-Z]$`). Un código válido que el modelo no vio se acepta y se codifica con frecuencia 0 |
| `primary_type` | uno de los 31 tipos que aparecen en el train del TP-final |
| `location_description` | opcional; vacío se codifica como `UNKNOWN` |
| `date` | fecha ISO 8601. Sin zona horaria se asume hora de Chicago; con zona se convierte |
| `latitude` · `longitude` | dentro de los límites de Chicago: [41.60, 42.05] y [-87.95, -87.50] |
| cualquier otro campo | se rechaza: el contrato no acepta campos extra |

Los textos se normalizan antes de validar: `" battery "` se acepta como `"BATTERY"`.

## Errores y observabilidad

- **503** si el modelo no se pudo cargar: la API igual levanta y lo informa en `/health`, en vez de morir al arrancar.
- **500 controlado** ante cualquier error inesperado. El cliente recibe un mensaje genérico; la traza completa queda en el log del servidor. Los mensajes de error nunca incluyen rutas del servidor ni detalles internos.
- **Una línea de log por request** con método, ruta, status, latencia y versión del modelo:

```
INFO:     GET /v1/metadata -> 200 en 4.2 ms (modelo v1)
INFO:     POST /v1/predict -> 200 en 31.9 ms (modelo v1)
INFO:     POST /v1/predict -> 422 en 0.2 ms (modelo v1)
```

Se ve que un 422 corta en la validación sin tocar el modelo, y por eso es dos órdenes de magnitud más rápido que una predicción real.

## Cliente de prueba

`make rest-client` recorre todos los endpoints y los casos inválidos, y devuelve código 1 si alguno no da el status esperado:

```
[OK] GET /health -> 200 (esperado 200)
[OK] GET /v1/metadata -> 200 (esperado 200)
[OK] POST /v1/predict con un payload válido -> 200 (esperado 200)
[OK] POST /v1/predict/batch con dos reportes -> 200 (esperado 200)
[OK] POST /v1/predict/batch con el lote vacío -> 422 (esperado 422)
[OK] POST /v1/predict, sin fecha -> 422 (esperado 422)
[OK] POST /v1/predict, primary_type desconocido -> 422 (esperado 422)
[OK] POST /v1/predict, latitud fuera de Chicago -> 422 (esperado 422)
[OK] POST /v1/predict, IUCR con formato inválido -> 422 (esperado 422)
[OK] POST /v1/predict, campo que no está en el contrato -> 422 (esperado 422)
```

## Cómo está armado

| archivo | qué tiene |
|---|---|
| `app.py` | `create_app()`: carga del modelo en el `lifespan`, middleware de log y 500, `/health` y el router `/v1` |
| `client.py` | cliente de prueba end-to-end |
| `Dockerfile` | `python:3.12-slim` + uv, instala solo el grupo `rest` y copia `arrest_model/`, `tp1_rest/` y `model/model.pkl` |

El modelo se carga una sola vez en el `lifespan` y queda en `app.state`; los endpoints solo leen de ahí. `create_app()` recibe el cargador como parámetro, y eso es lo que permite testear el 503 y el 500 sin tocar el archivo del modelo.
