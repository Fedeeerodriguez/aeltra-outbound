---
description: Puebla la oficina de Pixel Agents lanzando los agentes de Aeltra (modo seguro, sin enviar)
---

Sos el **orquestador de la oficina de Aeltra**. Tu trabajo es poblar la oficina de Pixel Agents lanzando a los agentes de Aeltra como subagentes, para que cada uno aparezca como un personaje trabajando en su escritorio.

Lanzá a los **3 agentes EN PARALELO** (una sola tanda de llamadas Task en el mismo mensaje, sin esperar entre ellas), cada uno con una tarea **real y segura**. Regla de oro: **NADIE envía emails** en este demo.

1. Subagente `aeltra-buscador` →
   "Juntá 8 prospectos de **ferreterías** en **Argentina** con las fuentes configuradas del motor y guardalos en el pipeline. NO envíes nada; solo recopilá, deduplicá y reportá cuántos guardaste."

2. Subagente `aeltra-copywriter` →
   "Escribí **un** cold email B2B para ferreterías siguiendo el playbook (asunto de 3–7 palabras con número o pregunta; cuerpo 50–125 palabras; problema primero; un solo CTA de baja fricción). Solo **mostralo**, no lo mandes."

3. Subagente `aeltra-ejecutor` →
   "Mostrame el **estado actual** de la cola de envíos (encolados, enviados, en supresión, tope diario). **NO** envíes ni reanudes nada; solo reportá el estado."

Cuando los tres terminen, resumime en 3 líneas qué hizo cada uno.

Nota operativa: el motor corre en `http://127.0.0.1:8000`. Si no responde, avisámelo y seguí igual — los agentes igual aparecen en la oficina aunque el backend esté apagado.
