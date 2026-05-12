# TrafficSim

> 🇬🇧 [English version](README.md)

Servidor de simulación de tráfico desarrollado para [CentralCore](https://github.com/marius-db/CentralCore). Genera una ciudad procedural con coches, semáforos y un sistema de vehículo de emergencia, y transmite el estado en tiempo real por WebSocket para que el módulo de tráfico de CentralCore pueda visualizarlo y controlarlo.

También abre una ventana pygame local para ver la simulación directamente sin necesidad de tener CentralCore corriendo.

---

## Qué hace

La simulación ejecuta una ciudad procedural sobre un grafo de intersecciones y calles. Hasta 500 coches la navegan usando Dijkstra, respetando los semáforos y manteniendo distancia con el coche de delante. La densidad de tráfico se calcula por arista cada tick y se retroalimenta al sistema de rutas para que los coches eviten naturalmente las calles congestionadas.

Los semáforos funcionan con un ciclo de fases NS/EW estándar con offsets aleatorios por intersección para que no se sincronicen todos a la vez.

Cuando CentralCore envía una ruta de vehículo de emergencia, el VE aparece en el punto de origen y la sigue a mayor velocidad. Los coches cercanos se apartan, y las intersecciones por delante reciben prioridad para despejar el camino. Cuando la ruta termina, todo vuelve a la normalidad.

El servidor envía dos tipos de mensajes:
- `map` una vez al conectar: el grafo completo de la ciudad (nodos, aristas, semáforos)
- `state` cada 80ms: posiciones de todos los coches, estados de semáforos, densidades de tráfico y estado del VE si está activo

CentralCore puede enviar tres tipos de comandos:
- `route`: iniciar una ruta de vehículo de emergencia entre dos IDs de nodo o coordenadas del mapa
- `cancel_route`: cancelar la ruta activa del VE
- `override_light`: forzar un semáforo concreto a un estado durante un tiempo determinado

---

## Requisitos

- Python 3.11 o superior
- pip

Instalar dependencias:

```
pip install websockets pygame fastapi
```

pygame es opcional. Si no está instalado el servidor funciona igualmente, simplemente no abre la ventana visual.

---

## Cómo ejecutarlo

```
python main.py
```

Eso es todo. El servidor arranca en `ws://localhost:8765` y la ventana pygame se abre junto a él.

Controles de la ventana pygame:

| Control | Acción |
|---------|--------|
| Scroll | Zoom |
| Clic izquierdo + arrastrar | Mover |
| R | Resetear zoom y posición |
| ESC o cerrar ventana | Salir |

---

## Estructura del proyecto

```
TrafficSim/
├── main.py          - punto de entrada, servidor WebSocket, manejo de comandos
├── simulation.py    - simulación principal: coches, semáforos, VE, bucle de tick
├── city.py          - generación procedural de la ciudad y rutas con Dijkstra
└── visualizer.py    - ventana pygame en un hilo daemon separado
```

---

## Cómo se genera la ciudad

La ciudad se construye a partir de una semilla fija para que el layout sea siempre el mismo. Se coloca una cuadrícula de 9x7 intersecciones principales con espaciado intencionalmente irregular para que no parezca una cuadrícula perfecta. Alrededor del 12% de las conexiones horizontales y verticales se eliminan para crear huecos naturales, y aproximadamente el 20% de los bloques de la cuadrícula reciben un atajo diagonal.

Las calles secundarias se generan entre intersecciones principales cercanas con 1 a 3 nodos intermedios cada una, desplazados perpendicularmente a la línea directa para que curven ligeramente. Cada calle secundaria recibe un nombre único tomado de un pool.

El resultado es una ciudad que parece real en lugar de generada, con grandes avenidas principales, calles secundarias más estrechas y cortes diagonales que crean atajos por la cuadrícula.

---

## Cómo funciona el tráfico

Cada coche recibe un destino aleatorio y usa Dijkstra para encontrar la ruta. Los coches tienen una variación de velocidad aleatoria (±12%) para que no se muevan todos de forma idéntica. Mantienen una distancia mínima con el coche de delante y reducen la velocidad progresivamente conforme se acercan en lugar de parar en seco.

En las intersecciones, los coches comprueban el semáforo de su dirección de aproximación y se detienen si está en rojo. La comprobación se activa dentro del último 15% del segmento de carretera o dentro de 50 unidades de la intersección, lo que sea mayor.

Cada 8 segundos se reconstruye la adyacencia de rutas usando las densidades de tráfico actuales como coste de arista, de modo que los coches se desvían naturalmente de las zonas congestionadas sin ninguna lógica explícita para ello.

---

## Cómo funciona el vehículo de emergencia

Cuando se envía una ruta, el VE aparece en el nodo de origen y sigue el camino Dijkstra a 130 unidades por segundo (frente a 88 de los coches en calles principales). A medida que avanza, las intersecciones dentro de 220 unidades por delante reciben prioridad: el semáforo en la dirección de aproximación del VE se pone en verde y los demás en rojo durante unos 15 segundos. Los coches dentro de 160 unidades se apartan y reducen su velocidad al 15% hasta que el VE pasa.

Cuando el VE llega a su destino, el servidor envía un mensaje `ev_done` y el VE se elimina. Todos los semáforos sobreescritos expiran por sus propios temporizadores.

---

## Protocolo WebSocket

### Mensajes enviados por el servidor

**map** (enviado una vez al conectar)
```json
{
  "type": "map",
  "nodes": [{"id": "n1", "x": 55.0, "y": 60.0, "main": true}, ...],
  "edges": [{"id": "e1", "from": "n1", "to": "n2", "lanes": 3, "main": true, "name": "Gran Via"}, ...],
  "lights": [{"id": "l1", "node": "n1", "dir": "N"}, ...]
}
```

**state** (enviado cada ~80ms)
```json
{
  "type": "state",
  "cars": [{"id": "c1", "x": 120.5, "y": 340.2, "na": "n3", "nb": "n4", "p": 0.42, "lane": 1}, ...],
  "lights": [{"id": "l1", "node": "n1", "dir": "N", "state": "green", "t": 11}, ...],
  "traffic": [{"id": "e1", "density": 0.34}, ...],
  "ev": null
}
```

**ev_done** (enviado cuando el VE llega al destino)
```json
{"type": "ev_done"}
```

### Comandos enviados por el cliente

**route**
```json
{"type": "route", "from": "n5", "to": "n42"}
```
o por coordenadas del mapa (hace snap al nodo principal más cercano):
```json
{"type": "route", "from_xy": [120.0, 340.0], "to_xy": [800.0, 600.0]}
```

**cancel_route**
```json
{"type": "cancel_route"}
```

**override_light**
```json
{"type": "override_light", "light_id": "l12", "state": "green", "dur": 30}
```

---

## Notas

La simulación es independiente y no tiene ninguna dependencia de CentralCore. Cualquier cliente WebSocket puede conectarse a ella. La ventana pygame y el servidor WebSocket corren de forma concurrente usando asyncio y un hilo daemon, así que cerrar la ventana pygame no para el servidor.

La semilla de la ciudad está fijada en 123 en `city.py`. Cambiarla genera un layout completamente diferente.