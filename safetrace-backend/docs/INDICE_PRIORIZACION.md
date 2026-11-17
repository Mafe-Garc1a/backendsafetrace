# Índice de priorización: ecuaciones y demostración

Este documento explica cómo SafeTrace calcula el índice de priorización con ecuaciones diferenciales y cómo mostrarlo funcionando, paso a paso.

- Código de las ecuaciones: [`core/modelos_indice.py`](../core/modelos_indice.py)
- Cálculo y guardado del índice: [`app/crud/ia_indice.py`](../app/crud/ia_indice.py)
- Parámetros por defecto: [`app/crud/configuracion.py`](../app/crud/configuracion.py)
- Decisión técnica: [`decisiones/0014-modelos-del-indice-de-priorizacion.md`](decisiones/0014-modelos-del-indice-de-priorizacion.md)
- Página de gráficas: [`graficas-indice.html`](graficas-indice.html)

> El índice es **orientativo**. Sirve para decidir qué inmuebles revisar primero después de un sismo; no reemplaza la evaluación de un perito (RF-68) y nunca cambia el estado del inmueble (RNF-37).

---

## 1. Idea general

Cuando ocurre un sismo, hay muchos inmuebles que revisar y pocos peritos. El índice ordena los inmuebles de 0 a 100: cuanto más alto, antes hay que revisarlo.

El índice combina **8 variables** (RF-67). Dos de ellas salen de ecuaciones diferenciales:

| Variable | Qué mide | De dónde sale |
|---|---|---|
| x₁ antigüedad | Años del inmueble | Dato del inmueble |
| x₂ sistema constructivo | Qué tan vulnerable es el tipo de estructura | Tabla de valores |
| **x₃ resonancia** | Cuánto amplifica el edificio el movimiento del suelo | **EDO de 2.º orden no homogénea** |
| x₄ magnitud | Tamaño del sismo | Dato del sismo |
| **x₅ cercanía al foco** | Qué tanta energía de la onda llega al inmueble | **Ecuación de onda** |
| x₆ antecedentes de daños | Daños registrados en la bitácora | Conteo de eventos |
| x₇ falta de mantenimiento | Pocos mantenimientos registrados | Conteo de eventos |
| x₈ tiempo sin revisión | Meses desde la última revisión | Fecha de la última revisión |

Además se usa la **vibración libre** (EDO de 2.º orden homogénea) para obtener el periodo y las frecuencias del edificio. La **fisura** (EDO de 1.er orden) está implementada pero no entra en el índice.

---

## 2. Flujo del cálculo

```
Sismo (SGC / USGS)
   │  n8n lo envía cada 5 minutos o menos
   ▼
POST /interno/sismos
   │  1. Guarda el sismo; si llega repetido, no lo duplica
   │  2. ¿Magnitud ≥ 5?  → es relevante
   │  3. Busca los inmuebles a 200 km o menos (fórmula del haversine)
   ▼
Para cada inmueble del radio:
   ├─ lo marca como «Marcado por evento sísmico»
   ├─ registra el evento en la bitácora
   ├─ CALCULA EL ÍNDICE  ← aquí se aplican las ecuaciones
   └─ notifica al propietario
```

El índice **solo se calcula cuando llega un sismo relevante**, nunca al consultarlo. Por eso, si no hay sismos, `GET /inmuebles/{id}/indice` responde «El inmueble aún no tiene índice calculado».

Dentro del cálculo el orden es:

1. **Reunir los datos:** año, sistema constructivo y número de pisos del inmueble; magnitud y profundidad del sismo; distancia del inmueble al epicentro; daños y mantenimientos de la bitácora; fecha de la última revisión.
2. **Aplicar los modelos:** periodo T, factor de resonancia F y distancia al foco R.
3. **Normalizar** las 8 variables a una escala de 0 a 1.
4. **Combinar** con los pesos: I = 100·Σ wᵢ·xᵢ.
5. **Guardar** el valor junto con las variables, los pesos, los parámetros y el aporte de cada variable, para poder explicar el índice aunque la configuración cambie después.

### Parámetros que usa el modelo

| Parámetro | Valor | Significado |
|---|---|---|
| ζ (zeta) | 0,05 | Razón de amortiguamiento (5 %, valor típico de edificios) |
| Tₛ | 0,6 s | Periodo dominante del suelo |
| Magnitud mínima | 5,0 | Desde aquí el sismo es relevante |
| Radio de afectación | 200 km | Inmuebles que se marcan |

ζ y Tₛ son **provisionales**: Tₛ debe confirmarse con la microzonificación sísmica de Pereira. Si en la base no existe el documento `parametros_indice`, se usan estos valores por defecto.

---

## 3. Las ecuaciones

El ejemplo que se usa en todo el documento es un **edificio de 5 pisos** y un **sismo de magnitud 6,2 a 80 km del inmueble y 30 km de profundidad**.

### 3.1 Vibración libre: EDO lineal homogénea de 2.º orden

Un edificio se modela como una masa **m** sobre un resorte de rigidez **k** con un amortiguador **c** (modelo de un grado de libertad). Si se desplaza y se suelta, su movimiento cumple:

$$
m\,x'' + c\,x' + k\,x = 0
$$

Dividiendo por m y usando $\omega_n = \sqrt{k/m}$ (frecuencia natural) y $\zeta = \dfrac{c}{2\sqrt{km}}$ (amortiguamiento):

$$
x'' + 2\zeta\omega_n\,x' + \omega_n^2\,x = 0
$$

**Ecuación característica:**

$$
\lambda^2 + 2\zeta\omega_n\lambda + \omega_n^2 = 0
\quad\Rightarrow\quad
\lambda = -\zeta\omega_n \pm i\,\omega_d,
\qquad \omega_d = \omega_n\sqrt{1-\zeta^2}
$$

Como ζ < 1 (caso **subamortiguado**), las raíces son complejas y la solución general es:

$$
x(t) = e^{-\zeta\omega_n t}\left(A\cos\omega_d t + B\sin\omega_d t\right)
$$

**Condiciones iniciales** x(0) = 1 (se desplaza una unidad) y x'(0) = 0 (se suelta sin velocidad):

- $x(0) = A = 1$
- $x'(0) = -\zeta\omega_n A + \omega_d B = 0 \;\Rightarrow\; B = \dfrac{\zeta\omega_n}{\omega_d}$

**Solución particular:**

$$
\boxed{x(t) = e^{-\zeta\omega_n t}\left[\cos\omega_d t + \frac{\zeta\omega_n}{\omega_d}\sin\omega_d t\right]}
$$

**Periodo del edificio.** No se conocen m ni k de cada inmueble, así que se usa la aproximación empírica:

$$
T \approx 0{,}1\cdot N \ \text{segundos} \qquad (N = \text{número de pisos}),
\qquad \omega_n = \frac{2\pi}{T}
$$

**Con el ejemplo (N = 5, ζ = 0,05):**

| Paso | Cálculo | Resultado |
|---|---|---|
| Periodo | T = 0,1 · 5 | **0,5 s** |
| Frecuencia natural | ωₙ = 2π / 0,5 | **12,566 rad/s** |
| Frecuencia amortiguada | ω_d = 12,566 · √(1 − 0,05²) | **12,551 rad/s** |
| Coeficiente B | 0,05 · 12,566 / 12,551 | 0,050 |
| Amplitud tras un ciclo | e^(−ζωₙT) = e^(−0,05·2π) | 0,73 |

Cada ciclo, la amplitud baja un 27 %: el edificio oscila y se va deteniendo. En la gráfica, la curva x(t) queda dentro de la envolvente $\pm e^{-\zeta\omega_n t}$.

**Para qué sirve en el índice:** da el periodo T, que se usa en la resonancia.

### 3.2 Resonancia: EDO lineal no homogénea de 2.º orden

Durante un sismo el suelo se mueve con aceleración $a_s(t)$. Visto desde el edificio, aparece una fuerza externa:

$$
m\,x'' + c\,x' + k\,x = -m\,a_s(t)
$$

Se supone que el suelo vibra de forma armónica con su periodo dominante Tₛ, es decir $a_s(t) = a_0\cos\omega t$ con $\omega = 2\pi/T_s$:

$$
x'' + 2\zeta\omega_n\,x' + \omega_n^2\,x = -a_0\cos\omega t
$$

**Solución:** $x(t) = x_h(t) + x_p(t)$.

- $x_h$ es la vibración libre de 3.1; se apaga con el tiempo por el factor $e^{-\zeta\omega_n t}$.
- Queda la respuesta **estacionaria** $x_p(t) = X\cos(\omega t - \varphi)$. Reemplazándola en la ecuación (coeficientes indeterminados) se obtiene su amplitud:

$$
X = \frac{a_0}{\omega_n^2}\cdot\frac{1}{\sqrt{(1-r^2)^2 + (2\zeta r)^2}},
\qquad r = \frac{\omega}{\omega_n} = \frac{T}{T_s}
$$

$a_0/\omega_n^2$ es el desplazamiento que tendría el edificio si la carga fuera estática. El cociente entre los dos es el **factor de amplificación dinámica**:

$$
\boxed{F = \frac{1}{\sqrt{(1-r^2)^2 + (2\zeta r)^2}}}
$$

**Interpretación:**

- r ≪ 1: el edificio es mucho más rígido que el suelo, F ≈ 1, no amplifica.
- **r ≈ 1: resonancia**, el periodo del edificio coincide con el del suelo. F llega a su máximo, ≈ 1/(2ζ) = **10**.
- r ≫ 1: el edificio es muy flexible, F < 1, se «aísla» del suelo.

**Con el ejemplo (T = 0,5 s, Tₛ = 0,6 s, ζ = 0,05):**

| Paso | Cálculo | Resultado |
|---|---|---|
| Relación de periodos | r = 0,5 / 0,6 | **0,833** |
| (1 − r²)² | (1 − 0,694)² | 0,0934 |
| (2ζr)² | (2 · 0,05 · 0,833)² | 0,0069 |
| Factor | F = 1 / √(0,0934 + 0,0069) | **3,157** |
| Variable del índice | x₃ = F / 5 | **0,631** |

El edificio de 5 pisos amplifica unas **3 veces** el movimiento del suelo porque está cerca de la resonancia. Se divide por 5 para llevar F a la escala de 0 a 1; si F > 5, x₃ vale 1.

### 3.3 Atenuación: ecuación de onda con simetría esférica

La onda sísmica sale del **foco** (hipocentro), bajo tierra, y se propaga en todas direcciones. Cumple la ecuación de onda:

$$
\frac{\partial^2 u}{\partial t^2} = v^2\,\nabla^2 u
$$

Con simetría esférica, u depende solo de la distancia R al foco y el laplaciano queda:

$$
\nabla^2 u = \frac{1}{R}\frac{\partial^2 (R\,u)}{\partial R^2}
$$

Haciendo el cambio $w = R\,u$, la ecuación se convierte en la ecuación de onda en una dimensión:

$$
\frac{\partial^2 w}{\partial t^2} = v^2\,\frac{\partial^2 w}{\partial R^2}
\quad\Rightarrow\quad
w = f\!\left(t - \frac{R}{v}\right)
$$

(solución de d'Alembert; se toma solo la onda que sale del foco). Volviendo a u:

$$
\boxed{u(R,t) = \frac{1}{R}\,f\!\left(t - \frac{R}{v}\right)}
$$

La forma de la onda viaja sin cambiar, pero **su amplitud cae como 1/R**: la energía se reparte en una esfera cada vez más grande.

**Distancia al foco.** El sistema conoce la distancia d en superficie (inmueble–epicentro) y la profundidad h del sismo. Por Pitágoras:

$$
R = \sqrt{d^2 + h^2}
$$

**Normalización:** se toma 20 km como referencia; a esa distancia o menos la variable vale 1:

$$
x_5 = \begin{cases} 1 & R \le 20 \text{ km} \\[4pt] \dfrac{20}{R} & R > 20 \text{ km} \end{cases}
$$

**Con el ejemplo (d = 80 km, h = 30 km):**

| Paso | Cálculo | Resultado |
|---|---|---|
| Distancia al foco | R = √(80² + 30²) = √7300 | **85,4 km** |
| Variable del índice | x₅ = 20 / 85,4 | **0,234** |

Al inmueble le llega cerca del 23 % de la amplitud que tendría a 20 km del foco.

### 3.4 Crecimiento de fisura: EDO de 1.er orden (informativa)

Si el ancho D de una fisura crece en proporción a su tamaño:

$$
\frac{dD}{dt} = k\,D
\quad\Rightarrow\quad
D(t) = D_0\,e^{kt}
$$

(ecuación de variables separables). Con dos mediciones, D₁ y D₂, separadas Δt meses:

$$
k = \frac{\ln(D_2/D_1)}{\Delta t}
$$

**Ejemplo:** una fisura pasa de 0,2 mm a 0,3 mm en 6 meses → k = ln(1,5)/6 = **0,068 por mes**; duplicaría su ancho en ln 2 / k ≈ 10 meses.

Está implementada (`tasa_crecimiento`), pero **no entra en el índice ni tiene endpoint**, porque el modelo de IA todavía no mide el ancho de las fisuras en milímetros.

---

## 4. Normalización y fórmula del índice

Cada variable se lleva a una escala de 0 a 1, donde 1 es lo más urgente. Si una cuenta da menos de 0 o más de 1, se recorta a ese rango.

| Variable | Fórmula | Vale 1 cuando… |
|---|---|---|
| x₁ antigüedad | (año actual − año de construcción) / 100 | Tiene 100 años o más |
| x₂ sistema constructivo | Valor de la tabla de abajo | Mampostería no reforzada o tapia |
| x₃ resonancia | F / 5 | F ≥ 5 |
| x₄ magnitud | (M − 5) / 3 | M ≥ 8 |
| x₅ cercanía al foco | 20 / R | R ≤ 20 km |
| x₆ antecedentes de daños | daños / 5 | 5 o más daños registrados |
| x₇ falta de mantenimiento | 1 − mantenimientos / 5 | Ningún mantenimiento registrado |
| x₈ tiempo sin revisión | meses / 24 | 2 años o más, o nunca revisado |

**Valores por sistema constructivo** (1 = más vulnerable). Solo mampostería no reforzada = 1 y pórticos de concreto = 0,4 vienen del documento base; los demás son propuestas del equipo:

| Sistema | Valor | Sistema | Valor |
|---|---|---|---|
| Mampostería no reforzada | 1,0 | Mampostería reforzada | 0,5 |
| Tapia / adobe | 1,0 | Madera | 0,5 |
| Bahareque | 0,8 | Pórticos de concreto | 0,4 |
| Otro | 0,7 | Muros de concreto | 0,3 |
| Mampostería confinada | 0,6 | Estructura metálica | 0,3 |

**Fórmula del índice:** un promedio ponderado multiplicado por 100.

$$
\boxed{I = 100\cdot\sum_{i=1}^{8}\frac{w_i}{\sum_j w_j}\,x_i}
$$

Los pesos se dividen por su suma, así que I siempre queda entre 0 y 100 aunque los pesos no sumen exactamente 1. El **aporte** de cada variable es $100\cdot\frac{w_i}{\sum w}\cdot x_i$, y la suma de los aportes es el índice.

### Ejemplo completo

Este es un inmueble **de ejemplo**, no uno de la base: 5 pisos, construido en 1985, mampostería confinada, con 1 daño y 2 mantenimientos registrados y sin revisiones. Sismo de M 6,2 a 80 km y 30 km de profundidad, calculado el 11 de noviembre de 2026. Se obtuvo ejecutando `calcular()` del sistema.

| Variable | Cálculo | xᵢ | Peso wᵢ | Aporte |
|---|---|---|---|---|
| x₁ antigüedad | (2026 − 1985) / 100 | 0,410 | 0,10 | 4,10 |
| x₂ sistema constructivo | Mampostería confinada | 0,600 | 0,15 | 9,00 |
| x₃ resonancia | 3,157 / 5 | 0,631 | 0,15 | 9,47 |
| x₄ magnitud | (6,2 − 5) / 3 | 0,400 | 0,15 | 6,00 |
| x₅ cercanía al foco | 20 / 85,4 | 0,234 | 0,20 | 4,68 |
| x₆ antecedentes de daños | 1 / 5 | 0,200 | 0,10 | 2,00 |
| x₇ falta de mantenimiento | 1 − 2/5 | 0,600 | 0,10 | 6,00 |
| x₈ tiempo sin revisión | Nunca revisado | 1,000 | 0,05 | 5,00 |
| **Índice** | | | **1,00** | **46,25** |

La variable que más pesa en este caso es la **resonancia** (9,47 puntos), que sale de la EDO no homogénea.

Los pesos también son **provisionales**. Se planea ajustarlos con las calificaciones de un perito sobre 20 a 30 inmuebles, por mínimos cuadrados con pesos no negativos.

---

## 5. Cómo hacer la demostración

### 5.1 Pruebas automáticas

En la terminal, desde la carpeta del backend:

```powershell
.\venv\Scripts\python.exe -m pytest tests/unit/test_modelos_indice.py tests/test_indice.py -v
```

Debe salir `10 passed`. Las pruebas comprueban cada ecuación con valores conocidos y que el índice se calcule al recibir un sismo.

### 5.2 Levantar la API

```powershell
uvicorn main:app --reload
```

Abrir http://localhost:8000/docs y pulsar **Authorize** con el correo y la contraseña del superadmin.

### 5.3 Anotar el inmueble

Con `GET /inmuebles`, anotar el **id** del inmueble y sus coordenadas. En `ubicacion.coordinates` viene primero la **longitud** y después la **latitud**.

### 5.4 Registrar un sismo de prueba

En producción los sismos llegan solos: **n8n** consulta los feeds del SGC y del USGS y los envía a la API. Ningún usuario los registra a mano. Para la demostración se simula ese envío.

1. Abrir `POST /interno/sismos` → **Try it out**.
2. En el campo **`x-credencial-servicio`** pegar el valor de `CREDENCIAL_SERVICIO_N8N` del archivo `.env`: solo lo que va después del `=`. No va en Authorize.
3. En el cuerpo, usar la longitud del inmueble y su latitud **+ 0,72**, que equivale a unos 80 km al norte:

```json
{
  "fuente": "SGC",
  "id_externo": "demo-001",
  "fecha_hora": "2026-11-11T10:00:00Z",
  "magnitud": 6.2,
  "profundidad_km": 30,
  "longitud": -75.69,
  "latitud": 5.53
}
```

4. **Execute.** Debe responder `"resultado": "NUEVO"` e `"inmuebles_marcados": 1`. Anotar el `_id` del sismo.

### 5.5 Consultar el índice

`GET /inmuebles/{inmueble_id}/indice`, en el grupo **«IA e índice de priorización»**:

| Campo | Qué contiene |
|---|---|
| `valor` | El índice, de 0 a 100 |
| `variables` | Los datos de entrada y los resultados de los modelos (`periodo_s`, `relacion_periodos`, `factor_resonancia`, `distancia_hipocentral_km`) |
| `variables_normalizadas` | Las 8 variables xᵢ entre 0 y 1 |
| `pesos` | Los pesos wᵢ usados |
| `aportes` | Puntos que suma cada variable |
| `parametros` | ζ y Tₛ usados |
| `aviso` | Que el índice es orientativo |

### 5.6 Ver las gráficas

1. Ejecutar `GET /inmuebles/{inmueble_id}/indice/modelos` y copiar todo el **Response body**.
2. Abrir [`graficas-indice.html`](graficas-indice.html) con doble clic (se abre en el navegador; necesita internet para cargar la librería de gráficas).
3. Pegar el JSON y pulsar **Graficar**. Sin datos, el botón **Ver el ejemplo de 5 pisos** muestra el ejemplo de este documento.

La página dibuja:

- **Vibración libre:** x(t) dentro de su envolvente.
- **Resonancia:** la curva F(r) con su pico en r = 1 y un punto en el inmueble.
- **Atenuación:** la amplitud 1/R frente a la distancia, con un punto en el inmueble.

Los datos pegados no se guardan: al cerrar la página hay que volver a pegarlos.

### 5.7 Priorización (opcional)

`GET /admin/sismos/{sismo_id}/priorizacion` lista los inmuebles del sismo de mayor a menor índice: el orden en que conviene revisarlos.

---

## 6. Problemas comunes

| Qué pasa | Causa | Solución |
|---|---|---|
| 401 «Credencial de servicio inválida» | El valor no coincide con el `.env` | Copiar sin espacios ni comillas; si se cambió el `.env`, reiniciar uvicorn |
| `"resultado": "DUPLICADO"` | Ese `id_externo` ya se usó | Cambiarlo: `demo-002`, `demo-003`… |
| `"inmuebles_marcados": 0` | El sismo quedó a más de 200 km, o la magnitud es menor que 5 | Revisar las coordenadas y la magnitud |
| 404 «aún no tiene índice calculado» | No ha llegado ningún sismo relevante cerca del inmueble | Registrar el sismo de prueba (5.4) |
| 409 «fórmula sin modelos» | El índice se calculó con una versión anterior de la fórmula | Registrar un sismo nuevo para recalcularlo |
| 422 | Falta un campo o un formato es incorrecto en el JSON | Revisar el cuerpo de la petición |
| La página no dibuja | No hay internet, o se pegó la respuesta de `/indice` en vez de `/indice/modelos` | Conectarse y pegar la respuesta correcta |

---

## 7. Limitaciones

- T ≈ 0,1·N es una aproximación general: sirve para priorizar, no para diseñar estructuras.
- El edificio se modela con un solo grado de libertad y el suelo con una vibración armónica.
- La atenuación 1/R ignora la absorción del terreno y los efectos locales del suelo.
- ζ, Tₛ, los pesos y la mayoría de los valores por sistema constructivo son provisionales.
- El índice ordena revisiones; la evaluación del daño la hace siempre un perito.
