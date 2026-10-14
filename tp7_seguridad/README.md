# Mini-TP 7 — El modelo, asegurado

El mismo modelo de arrestos de Chicago que sirven las APIs del repo, ahora detrás de autenticación, autorización por rol, límite de tasa y un registro de auditoría. El marco es [SAIF](https://safety.google/cybersecurity-advancements/saif/), el *Secure AI Framework* de Google.

← [README general del repo](../README.md) · [Mini-TP 1 (REST)](../tp1_rest/README.md) · [Mini-TP 2 (GraphQL)](../tp2_graphql/README.md) · [Mini-TP 3 (gRPC)](../tp3_grpc/README.md) · [Mini-TP 4 (streaming)](../tp4_streaming/README.md) · [Mini-TP 5 (federado)](../tp5_federated/README.md) · [Mini-TP 6 (data lake)](../tp6_datalake/README.md)

## Cómo correrlo

No necesita ningún servicio levantado: el notebook arma las APIs en proceso con `TestClient`.

```bash
make install
uv run jupyter lab tp7_seguridad/mini_tp7_actividad.ipynb
```

El notebook se entrega ejecutado, con sus salidas.

## Qué muestra

La capa elegida es REST, que es por donde la plataforma del integrador expone el modelo. El notebook va de la versión sin ninguna protección a la asegurada:

| | antes | después |
|---|---|---|
| sin token | 200, predice | **401** |
| token vencido | 200, predice | **401** |
| rol no autorizado | 200, predice | **403** |
| reporte fuera de Chicago | 200, probabilidad sin sentido | **422** |
| mil consultas seguidas | las mil pasan | **429** después de cinco |
| quién preguntó qué | no queda registro | registro con hash, sin datos personales |

## Los cuatro controles

**Autenticación con JWT.** El token lleva quién es y con qué rol, firmado y con quince minutos de vencimiento. Lo que limita el daño de una credencial filtrada es cuánto dura, no cuán largo sea el secreto. El algoritmo va declarado en `jwt.decode`: aceptar el que viene adentro del token es la vulnerabilidad clásica de JWT, porque permite presentar uno firmado con `none`.

**Autorización por rol.** Solo `analista` y `admin` piden predicciones. Un token válido con otro rol recibe 403, no 401: la diferencia importa porque le dice al cliente que su credencial está bien pero no alcanza.

**Límite de tasa.** Cinco por minuto y por usuario del token, no por IP: detrás de un proxy todas las consultas llegan con la misma IP, así que limitar por IP castigaría a todos por el abuso de uno.

**Registro de auditoría.** Timestamp, usuario, hash de la entrada, predicción, probabilidad y versión del modelo. Guarda el **hash** y no el reporte: un reporte trae la latitud y la longitud de un hecho, así que conservarlo entero convertiría el registro en una segunda base de datos personales, que es justo lo que la auditoría debería proteger. Con el hash alcanza para lo que sirve: probar que dos consultas fueron por lo mismo y atar cada respuesta a su entrada.

## La validación es el contrato de verdad

El notebook de la cátedra propone validar con una lista de floats de largo fijo. Acá la entrada es `CrimeReport`, el contrato que comparten los cuatro protocolos del repo, con sus rangos ya puestos. Validar en el notebook es validar con lo mismo que valida producción.

Y eso es seguridad, no solo calidad, porque **un modelo no avisa cuando le dan algo fuera de su dominio: responde igual y con la misma confianza**. Con latitud 0 —el Golfo de Guinea— la codificación calcula la distancia a la comisaría más cercana de Chicago, que son miles de kilómetros, y el modelo devuelve una probabilidad que parece seria. El contrato la rechaza antes de que el modelo la vea.

## Por qué el límite de tasa casi no molesta acá

Frena la extracción del modelo: un atacante que consulta sin límite reconstruye la frontera de decisión preguntando, y se lleva un sustituto sin tocar el artefacto.

Y el costo para un consumidor legítimo es cero, porque conocemos el volumen: la plataforma procesa **633 reportes por día**, o sea 0,007 por segundo. Nadie que use el servicio para lo que fue hecho se acerca a cinco por minuto.

## Qué falta para llevarlo al integrador

Las conclusiones del notebook lo detallan. En resumen, tres cosas cambian al salir del notebook:

- el estado del límite vive en memoria del proceso, así que con más de una réplica el límite efectivo se multiplica;
- la auditoría en una lista se pierde al reiniciar, y un registro que se borra solo no es un registro de auditoría;
- y el agujero más grande de la plataforma no es la API: los servicios del compose comparten la credencial root de MinIO. Asegurar la API y dejar esa credencial sería asegurar la puerta y abrir la ventana.
