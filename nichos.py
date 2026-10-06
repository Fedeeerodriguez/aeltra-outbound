# -*- coding: utf-8 -*-
"""Catálogo de NICHOS para la máquina de prospección con evidencia (mystery shopper).

Cada nicho trae:
  - queries:       términos de Google Maps (se les agrega la zona en la rotación).
  - dolor:         el problema concreto que atacamos (para el copy y la demo).
  - quejas_clave:  palabras EXTRA (además de las globales del auditor) que delatan
                   la falla de ese rubro en las reseñas de Google.
  - canal:         vía de contacto preferida para el cierre (whatsapp / email).
  - demo_pitch:    qué muestra la demo personalizada de ese rubro.
  - pasos:         secuencia de 3 mails (asunto + cuerpo). Usan {{empresa}}, {{nombre}},
                   {{bloque_evidencia}} (lo inyecta el worker con la evidencia de la
                   auditoría; si no hay, queda vacío y el mail igual se lee bien) y
                   {{firma}} (lo pone el motor con el nombre del remitente real).

Filosofía de marca (ver vault Quienes-somos): "La tecnología se adapta a vos".
No vendemos un software-paquete: vendemos reestructuración operativa a medida para que
la operación mejore de forma exponencial con el mínimo cambio y esfuerzo.
"""

# Bloque de valor reutilizable (cierre del paso 1). Formal-humano, usted, sin jerga.
_VALOR = (
    "En Aeltra no vendemos un sistema al que haya que amoldarse. Montamos la automática "
    "sobre cómo ya trabajan ustedes: se adapta a ustedes, no al revés, con el mínimo cambio."
)

# CTA de baja fricción (comparten todos los pasos 1).
_CTA = "¿Le muestro en 10 minutos, sobre {{empresa}}, cómo quedaría? Sin compromiso."

CALENDLY = "https://calendly.com/fedeeerodriguez/calendario-personal-federico-rodriguez"


def _pasos(saludo_dolor, p2_gancho, p3_cierre):
    """Arma los 3 pasos estándar a partir de 3 frases propias del nicho."""
    return [
        {
            "asunto": "Una consulta sobre {{empresa}}",
            "cuerpo": (
                "Hola {{nombre}}, le escribo de Aeltra.\n\n"
                f"{saludo_dolor}\n\n"
                "{{bloque_evidencia}}"
                f"{_VALOR}\n\n"
                f"{_CTA}\n\n"
                "{{firma}}"
            ),
        },
        {
            "asunto": "Retomo — {{empresa}}",
            "cuerpo": (
                "Hola {{nombre}}, le dejo esto arriba por si se le traspapeló.\n\n"
                f"{p2_gancho}\n\n"
                "No es un chatbot genérico: contesta como lo haría alguien de {{empresa}}, "
                "con la info real del negocio, y le pasa a usted solo lo que vale la pena.\n\n"
                "¿Le viene bien una llamada corta esta semana?\n\n"
                "{{firma}}"
            ),
        },
        {
            "asunto": "¿Lo dejo por acá, {{empresa}}?",
            "cuerpo": (
                "Hola {{nombre}}, no quiero insistir de más.\n\n"
                f"{p3_cierre}\n\n"
                "Si le interesa verlo, agenda cuando quiera acá: " + CALENDLY + "\n"
                "Y si no es el momento, perfecto — no le escribo más.\n\n"
                "{{firma}}"
            ),
        },
    ]


NICHOS = {
    "inmobiliarias": {
        "nombre": "Inmobiliarias",
        "queries": ["inmobiliaria", "inmobiliarias"],
        "dolor": "consultas de alquiler/venta que llegan fuera de hora y se enfrían sin respuesta",
        "quejas_clave": ["no muestran", "no coordinan", "no responden por la propiedad",
                         "nunca me mostraron", "no envían información", "no mandan info"],
        "canal": "whatsapp",
        "demo_pitch": ("un asistente que responde al instante cada consulta de una propiedad "
                       "(precio, requisitos, visita) y agenda la muestra, 24/7"),
        "pasos": _pasos(
            "En inmobiliarias la mayoría de las consultas de una propiedad llegan de "
            "noche o fin de semana, y la que no se contesta en minutos se va a otra. "
            "Es plata que entra por la puerta y se va sin que nadie la vea.",
            "La idea es simple: cada consulta por una propiedad se responde al toque "
            "(precio, requisitos, coordinar visita) aunque sea domingo a la noche.",
            "Lo que resolvemos es que ninguna consulta de una propiedad quede sin "
            "respuesta — que es donde hoy se pierden las operaciones.",
        ),
    },
    "estetica": {
        "nombre": "Clínicas y centros de estética",
        "queries": ["centro de estetica", "clinica estetica", "dermatologia estetica"],
        "dolor": "turnos que se pierden porque la consulta no se responde a tiempo",
        "quejas_clave": ["no dan turno", "no contestan para turnos", "imposible sacar turno",
                         "no responden para reservar", "nunca me dieron turno"],
        "canal": "whatsapp",
        "demo_pitch": ("un asistente que responde consultas de tratamientos y precios y "
                       "reserva el turno al instante, también fuera de horario"),
        "pasos": _pasos(
            "En estética la consulta es por impulso: la persona pregunta por un "
            "tratamiento y, si no le responden en el momento, se enfría o va a otro lado. "
            "Cada turno que no se contesta a tiempo es facturación que no entra.",
            "La idea: que cada consulta de tratamiento se responda al instante con "
            "precios e info, y deje el turno reservado — sin depender de que haya "
            "alguien libre para contestar.",
            "Lo que resolvemos es que la recepción no pierda turnos por estar ocupada "
            "o fuera de horario.",
        ),
    },
    "odontologia": {
        "nombre": "Consultorios odontológicos",
        "queries": ["consultorio odontologico", "odontologia", "dentista"],
        "dolor": "llamadas y mensajes de pacientes que quedan sin contestar",
        "quejas_clave": ["no atienden el telefono", "no dan turno", "nunca atienden",
                         "no contestan para urgencias"],
        "canal": "whatsapp",
        "demo_pitch": ("un asistente que atiende consultas y urgencias, informa y agenda "
                       "turnos sin que el equipo tenga que frenar lo que está haciendo"),
        "pasos": _pasos(
            "En un consultorio el teléfono suena mientras se está atendiendo, y muchas "
            "consultas de pacientes nuevos quedan sin contestar. Ese paciente que no "
            "logró comunicarse, llama al de la otra cuadra.",
            "La idea: que cada consulta de un paciente se responda al instante y quede "
            "el turno agendado, sin frenar la atención del box.",
            "Lo que resolvemos es que no se pierdan pacientes nuevos por una llamada "
            "que no se pudo atender.",
        ),
    },
    "servicios_hogar": {
        "nombre": "Servicios del hogar (plomería, electricistas, aires, cerrajería)",
        "queries": ["plomero", "electricista", "service aire acondicionado", "cerrajeria"],
        "dolor": "pedidos urgentes que, si no se contestan al toque, se los lleva otro",
        "quejas_clave": ["no vino", "no apareció", "no responde urgencias", "nunca vino",
                         "no se presentó", "quedé esperando"],
        "canal": "whatsapp",
        "demo_pitch": ("un asistente que toma el pedido urgente al instante, pide los datos "
                       "clave y coordina la visita aunque sea de madrugada"),
        "pasos": _pasos(
            "En este rubro el que contesta primero gana el trabajo. La urgencia que "
            "no se responde en minutos se la lleva el próximo de la lista. Cada mensaje "
            "sin contestar es un trabajo perdido.",
            "La idea: que todo pedido urgente se tome al instante (qué pasa, dónde, "
            "cuándo) y le llegue a usted ya ordenado para salir.",
            "Lo que resolvemos es que no se pierdan trabajos por no llegar a contestar "
            "a tiempo.",
        ),
    },
    "concesionarias": {
        "nombre": "Concesionarias y venta de usados",
        "queries": ["concesionaria", "venta de autos usados", "agencia de autos"],
        "dolor": "consultas por una unidad que se enfrían sin seguimiento",
        "quejas_clave": ["no responden por el auto", "no dan información del vehículo",
                         "nunca me contactaron", "no hacen seguimiento"],
        "canal": "whatsapp",
        "demo_pitch": ("un asistente que responde por cada unidad (precio, km, financiación) "
                       "y arma el seguimiento del interesado hasta que agenda ver el auto"),
        "pasos": _pasos(
            "Cuando alguien pregunta por una unidad está caliente, pero si no se le "
            "responde rápido y no hay seguimiento, en dos días ya compró en otro lado. "
            "El lead existe; lo que falta es contestarlo a tiempo.",
            "La idea: responder cada consulta por un vehículo al instante (precio, "
            "financiación, estado) y no soltar al interesado hasta que agenda verlo.",
            "Lo que resolvemos es que ningún interesado en una unidad quede sin "
            "seguimiento.",
        ),
    },
    "turismo": {
        "nombre": "Hotelería, cabañas y turismo",
        "queries": ["cabañas", "hotel", "complejo turistico", "posada"],
        "dolor": "consultas de reserva que llegan fuera de hora y no se responden",
        "quejas_clave": ["no responden para reservar", "no contestan consultas",
                         "nunca me confirmaron", "no respondieron la reserva"],
        "canal": "whatsapp",
        "demo_pitch": ("un asistente que responde disponibilidad y tarifas al instante y "
                       "deja la reserva encaminada, a cualquier hora"),
        "pasos": _pasos(
            "En turismo la gente consulta de noche y planificando: si no recibe "
            "disponibilidad y precio en el momento, reserva en el lugar que sí le "
            "respondió. La consulta que no se contesta es una noche vacía.",
            "La idea: responder disponibilidad y tarifas al instante y dejar la reserva "
            "encaminada, sin importar la hora.",
            "Lo que resolvemos es que no se pierdan reservas por no contestar a tiempo.",
        ),
    },
}


def get(nicho_key):
    return NICHOS.get((nicho_key or "").strip().lower())


def listar():
    return [{"key": k, "nombre": v["nombre"], "dolor": v["dolor"], "canal": v["canal"]}
            for k, v in NICHOS.items()]
