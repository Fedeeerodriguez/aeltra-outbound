# -*- coding: utf-8 -*-
"""Puente a los agentes .md de Claude Code: los dispara en headless (claude -p --agent)."""
import os
import json
import shutil
import subprocess

import config
import activity

CLAUDE_BIN = shutil.which("claude")
if not CLAUDE_BIN:
    _fallback = r"C:\Users\Usuario\AppData\Roaming\npm\claude.cmd"
    CLAUDE_BIN = _fallback if os.path.exists(_fallback) else None

# mapea el agente .md al slot de actividad de la dashboard
_ACT = {
    "aeltra-buscador": "busqueda",
    "aeltra-copywriter": "copywriter",
    "aeltra-ejecutor": "ejecutor",
    "aeltra-orquestador": "orquestador",
}

def act_slot(agente):
    return _ACT.get(agente, "orquestador")


def run_agent(agente, objetivo, budget=1.0, timeout=600):
    """Corre un agente .md de Claude Code en headless y devuelve su resultado."""
    slot = act_slot(agente)
    if not CLAUDE_BIN:
        msg = "El CLI de Claude Code no está en este entorno (server). Usá el motor Python."
        activity.update(slot, "error", msg)
        return {"ok": False, "error": msg}
    activity.update(slot, "trabajando", f"Claude Code · {agente} ejecutando (Claude Max)…")
    # Usar la suscripcion (Claude Max) en vez de la API: quitamos la key del subproceso.
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    try:
        proc = subprocess.run(
            [CLAUDE_BIN, "-p", objetivo, "--agent", agente,
             "--permission-mode", "bypassPermissions",
             "--output-format", "json"],
            cwd=config.BASE_DIR, capture_output=True, text=True, timeout=timeout, env=env,
        )
        result = ""
        try:
            result = json.loads(proc.stdout).get("result", "")
        except Exception:
            result = (proc.stdout or "")[-1500:]
        ok = proc.returncode == 0
        _titulos = {"copywriter": "Copy que escribió", "busqueda": "Búsqueda realizada",
                    "orquestador": "Campaña armada", "ejecutor": "Envíos"}
        res_txt = result if ok else ((proc.stderr or result or "")[-1500:])
        activity.update(slot, "listo" if ok else "error",
                        f"Claude Code · {agente}: {'terminó ✅' if ok else 'falló'}",
                        resultado=res_txt, titulo=_titulos.get(slot, "Resultado"))
        try:
            import pipeline
            pipeline.log_agente(slot, objetivo, res_txt, ok)
        except Exception:
            pass
        return {"ok": ok, "resultado": result,
                "error": (proc.stderr or "")[-500:] if not ok else None}
    except subprocess.TimeoutExpired:
        activity.update(slot, "error", f"Claude Code · {agente}: timeout")
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        activity.update(slot, "error", f"Claude Code · {agente}: {e}")
        return {"ok": False, "error": str(e)}
