# Model card: `chicago-arrest-xgboost`

Qué hace el modelo que sirve la plataforma, con qué datos se entrenó, qué tan bien anda y en qué casos no hay que usarlo. Los números son los de la versión con el alias `champion` al 15/10/2026, la v2 del registro, la que dejó el entrenamiento que disparó la última corrida del ETL, y salen del registro de MLflow y de la partición curada con la que se entrenó.

## Qué es

| | |
|---|---|
| nombre en el registro | `chicago-arrest-xgboost`, alias `champion` |
| algoritmo | `XGBClassifier` con los hiperparámetros por defecto y `scale_pos_weight` calculado del dato (5,46 en esta versión) |
| entrada | los 6 campos crudos de un reporte: `iucr`, `primary_type`, `location_description`, `date`, `latitude`, `longitude` |
| features | 7, que el modelo calcula adentro: frecuencia de IUCR, de tipo primario y de lugar, seno del día, X e Y proyectadas y estandarizadas, y distancia a la comisaría más cercana |
| salida | probabilidad de que el reporte haya terminado en arresto, y la decisión binaria con el umbral del modelo |
| umbral | 0,80, elegido sobre validación maximizando MCC y guardado con el modelo |
| dueño | la cátedra de Operaciones de Aprendizaje Automático II, CEIA–FIUBA |

El modelo viaja con su propia codificación: las frecuencias, los escaladores y las comisarías son parte del artefacto, no del pipeline. Por eso recibe campos crudos y no features ya calculadas.

## Para qué se puede usar

Para estimar, sobre un reporte de crimen de la ciudad de Chicago, qué tan parecido es a los reportes que terminaron en arresto. Sirve como herramienta de análisis agregado: comparar períodos, tipos de delito o zonas.

**Para qué no.** Para decidir sobre una persona (a quién detener, a quién vigilar, a quién asignar recursos policiales) no sirve, y usarlo así es el daño concreto que este modelo puede hacer. Tampoco sirve fuera de Chicago, ni para reportes anteriores o muy posteriores a la ventana con la que se entrenó.

## Datos

| | |
|---|---|
| fuente | portal de datos abiertos de Chicago, dataset `ijzp-q8t2`, más las comisarías de `z8bn-74gv` |
| ventana | los últimos 365 días de reportes, por particiones mensuales |
| partición curada | `2026-10-15` |
| entrenamiento | 177.863 filas, 15,47% con arresto |
| prueba | 44.472 filas, 15,50% con arresto |
| validación | 26.680 filas, separadas del entrenamiento solo para elegir el umbral |

El modelo final se reajusta sobre el entrenamiento completo, después de elegir el umbral.

## Métricas

Medidas sobre el conjunto de prueba, con el umbral con el que el modelo decide.

| métrica | valor |
|---|---|
| MCC | 0,5716 |
| AUC | 0,8855 |
| accuracy | 0,9013 |
| precision (ponderada) | 0,8950 |
| recall (ponderado) | 0,9013 |
| F1 (ponderado) | 0,8900 |

**La métrica que importa es MCC.** Precision, recall y F1 son promedios ponderados por soporte, así que los domina la clase mayoritaria: con un 15% de positivos, predecir "no hubo arresto" siempre ya da 0,85 de accuracy. MCC mira las cuatro celdas de la matriz de confusión y no se deja engañar por el desbalance.

## El umbral

Decidir en 0,5 (lo que hacía el pipeline heredado) da MCC 0,4671 y accuracy 0,8004 sobre el mismo test. Elegirlo sobre validación lo sube a 0,5716 y 0,9013.

Es estable: repitiendo la elección 12 veces sobre la misma ventana, cada una con otro 15% de validación, el umbral cae entre 0,76 y 0,83 (media 0,797, desvío 0,019) y el MCC resultante en test entre 0,5753 y 0,5816 (desvío 0,0017). O sea que la elección del umbral mueve el resultado mucho menos que la diferencia contra el 0,5 fijo.

El umbral viaja dentro del artefacto y se publica en `GET /v1/metadata`, para que un consumidor pueda reproducir la decisión o aplicar su propia política sobre la probabilidad.

## Consideraciones éticas

El modelo predice **arrestos, no delitos**. La etiqueta registra lo que hizo la policía, no lo que pasó: dos reportes idénticos pueden diferir en si hubo arresto por la zona, el turno o la dotación. Entrenar sobre esa etiqueta hace que el modelo aprenda el patrón de actuación policial, con sus sesgos históricos incluidos.

Dos de las siete features son las coordenadas del hecho y una tercera es la distancia a la comisaría más cercana, así que la geografía pesa fuerte, y en Chicago la geografía está correlacionada con la composición racial y el nivel socioeconómico de los barrios. Usar las predicciones para dirigir el despliegue policial realimentaría ese patrón: más presencia donde el modelo predice más arrestos, más arrestos donde hay más presencia.

No se midió el desempeño por grupo (ni por distrito ni por tipo de delito), así que no hay evidencia de que el error esté repartido parejo. Es lo primero que habría que medir antes de darle cualquier uso operativo.

Los datos de entrada son públicos y están agregados por el portal, pero un reporte individual trae latitud y longitud de un hecho: por eso el registro de auditoría del servicio guarda un hash de la entrada y no la entrada.

## Limitaciones

- **Dominio cerrado.** El contrato rechaza coordenadas fuera de Chicago con 422. Un reporte fuera de rango no obtiene una predicción mala, no obtiene ninguna.
- **Categorías nuevas.** Un IUCR o un lugar que el modelo no vio se codifican con frecuencia 0, como hizo el entrenamiento con el test. La predicción es válida pero menos informada.
- **Deriva.** El entrenamiento compara la distribución nueva contra la del champion y registra la deriva como métricas (`drift_max_sigma`, `drift_freq_new_categories`). En esta versión dieron 0: la ventana no se movió.
- **Retraso del portal.** Los reportes se publican con unos doce días de atraso, así que ninguna versión puede ser más fresca que eso.
- **Reentrenamiento.** Mensual, con el ETL. A 633 reportes por día, un mes agrega un 8% sobre la ventana. Reentrenar a diario cambiaría menos que el ruido de la propia elección del umbral.

## Cómo se audita una predicción

Cada respuesta trae `model_version`. Con ese número se llega al run de MLflow que la entrenó, y de ahí a la partición curada, las métricas y el umbral. El grafo de linaje en Neo4j completa el camino hacia atrás hasta las particiones crudas que la produjeron, y hacia adelante desde una partición cruda hasta las versiones que la usaron.

Del lado del servicio, cada request deja una línea con el usuario, el status, la versión del modelo y el hash de la entrada: ver [la arquitectura](arquitectura.md#seguridad-del-servicio).
