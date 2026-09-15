# Medición de latencia: gRPC contra REST

Detalle de la comparación entre las dos APIs del repo, que sirven el mismo modelo de arrestos de Chicago. La reflexión con las conclusiones está en el [notebook](mini_tp3_actividad.ipynb); acá está el método y la lectura de los números.

← [Mini-TP 3](README.md)

## Qué se midió

Las dos APIs hacen el mismo trabajo por llamada: validar el reporte, codificar las 7 features y predecir. Lo único que cambia es el protocolo, así que la diferencia medida es de transporte y serialización.

Se midieron cuatro cohortes:

| cohorte | qué es |
|---|---|
| `rest-local` | la API REST como proceso en la máquina |
| `grpc-local` | el servicio gRPC como proceso en la máquina |
| `rest-dockerizado` | la API REST en contenedor |
| `grpc-dockerizado` | el servicio gRPC en contenedor |

Las cohortes locales se midieron con los dos servicios locales, y las dockerizadas con los dos en contenedor al mismo tiempo. Nunca se compara una cohorte local contra una dockerizada de otro protocolo: eso mediría el empaquetado y no el protocolo.

A cada cohorte se le tomaron dos pruebas: una llamada suelta, repetida 300 veces, y un lote de 100 reportes. De REST se miden además dos formas de conectarse, abriendo la conexión en cada llamada y reutilizándola, porque gRPC siempre reutiliza el canal y la comparación pareja es contra esa segunda forma.

Cada cohorte se midió tres veces, porque con una sola medición no se distingue un efecto real del ruido. La tabla muestra la mediana de esas tres corridas; los valores crudos están en [`latencias.json`](latencias.json).

## Resultados

| cohorte | prueba | variante | mediana (ms) |
|---|---|---|---|
| `rest-local` | una llamada | sin sesión | 2.78 |
|  | una llamada | keep-alive | 2.66 |
|  | lote de 100 | 100 llamadas sueltas | 255.83 |
|  | lote de 100 | 1 llamada al batch | 3.32 |
| `rest-dockerizado` | una llamada | sin sesión | 5.63 |
|  | una llamada | keep-alive | 4.94 |
|  | lote de 100 | 100 llamadas sueltas | 507.65 |
|  | lote de 100 | 1 llamada al batch | 6.92 |
| `grpc-local` | una llamada | canal reusado | 1.85 |
|  | lote de 100 | 1 PredictStream | 6.46 |
| `grpc-dockerizado` | una llamada | canal reusado | 2.81 |
|  | lote de 100 | 1 PredictStream | 13.46 |

## Qué se repite

Estos efectos aparecen con rangos separados entre condiciones, o sea que se distinguen del ruido:

- gRPC contra REST con keep-alive da entre 1.40x y 1.56x local, y entre 1.76x y 1.90x dockerizado. La ventaja de gRPC se agranda dentro de Docker.
- Dockerizar cuesta caro, y no por igual: la mediana empeora 102% en REST sin sesión, 86% en REST con keep-alive y 52% en gRPC. gRPC aguanta bastante mejor, pero está lejos de ser inmune.
- Agrupar es lo que más mueve la aguja: 100 llamadas sueltas contra una sola llamada al lote da entre 47x y 83x, en las dos condiciones.
- El lote por REST le gana al streaming de gRPC en las seis corridas.

## Qué no se puede concluir

Que la ventaja del lote sobre el streaming dependa de dockerizar: da entre 1.51x y 2.11x local, contra 1.77x y 2.76x dockerizado, o sea rangos superpuestos. La dirección se repite siempre, pero la magnitud no se distingue del ruido.

Los números varían entre corridas, y bastante: es una laptop con Docker Desktop y no un banco de pruebas. Sirven para comparar rangos, no para la tercera cifra. Por eso tampoco se mezclan mediciones de sesiones distintas: la tabla es una única tanda, medida de corrido.

## Otras mediciones

El mismo reporte pesa 60 bytes serializado en protobuf contra 161 en JSON compacto, unas 2.7 veces menos, porque en protobuf viajan los números de campo y no sus nombres.

En un lote de 100 por streaming, la primera predicción llega bastante antes que la última: el servidor puntúa el lote de una y después emite los mensajes, así que el cliente puede empezar a trabajar sin esperar a que lleguen todos.

## Cómo reproducirla

Desde la raíz del repo, con los dos servicios levantados del mismo lado:

```bash
# cohortes locales
uv run uvicorn tp1_rest.app:app --port 8000 &
uv run python -m tp3_grpc.server &
make grpc-bench

# cohortes dockerizadas
make rest-up && make grpc-up
make grpc-bench
```
