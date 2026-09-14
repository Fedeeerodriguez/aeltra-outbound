# -*- coding: utf-8 -*-
"""Registro en vivo de qué está haciendo cada agente (para la pestaña Agentes)."""
import threading
import copy as _copy
from datetime import datetime

_LOCK = threading.Lock()

AGENTES = ["orquestador", "busqueda", "copywriter", "ejecutor"]

def _blank():
    return {"estado": "idle", "mensaje": "En espera", "progreso": None,
            "actualizado": None, "log": []}

_STATE = {a: _blank() for a in AGENTES}


def update(agente, estado=None, mensaje=None, progreso=None):
    """Actualiza el estado de un agente. estado: idle|trabajando|listo|error."""
    with _LOCK:
        s = _STATE.setdefault(agente, _blank())
        if estado is not None:
            s["estado"] = estado
        if mensaje is not None:
            s["mensaje"] = mensaje
            s["log"].append({"t": datetime.now().strftime("%H:%M:%S"), "m": mensaje})
            s["log"] = s["log"][-15:]
        if progreso is not None:
            s["progreso"] = progreso
        s["actualizado"] = datetime.now().strftime("%H:%M:%S")


def snapshot():
    with _LOCK:
        return _copy.deepcopy(_STATE)
