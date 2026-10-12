# Archivos visuales del proyecto

Esta carpeta es para material de trabajo **antes** de que llegue a la app.
No es lo mismo que `static/img/`, que es donde viven los archivos que el
navegador realmente carga cuando alguien usa Empacadora San Juan.

## Como esta organizada

- **`reference/`** — mockups, capturas de pantalla, ideas de diseno e
  imagenes de inspiracion (por ejemplo las que ya usamos: "Ideas para APP
  Empacadora San Juan.jpg", "Ideas de APP Verdura.jpg", "Volcan Irazu.jpg").
  Sirven para que Kodak entienda hacia donde vamos, pero nunca se sirven
  directo desde la app.

- **`photos/`** — fotos reales del negocio: la planta, el brocoli/coliflor,
  el volcan, los empleados (con su permiso), etc. Cuando una foto de aqui
  se vaya a usar de verdad en la app, se optimiza (comprime/recorta) y se
  copia a `static/img/` con un nombre claro.

- **`logos/`** — el logo de Empacadora San Juan y/o de Veltyk en sus
  formatos originales (SVG, AI, PNG en alta resolucion), para no perder
  la version editable si algun dia hay que ajustarlo.

## Regla simple

Si el archivo es algo que el navegador debe cargar cuando alguien visita
la app -> va en `static/img/`.

Si el archivo es material de trabajo, referencia, o el original de alta
resolucion antes de optimizar -> va aqui, en la subcarpeta que le
corresponda.

## Nota sobre tamano en Git

Fotos reales (JPG/PNG de camara o celular) pueden pesar varios MB cada
una. Si esta carpeta empieza a crecer mucho, avisale a Kodak para
considerar Git LFS o simplemente no commitear los originales pesados
(dejarlos solo en local/OneDrive y commitear nada mas las versiones ya
optimizadas en `static/img/`).
