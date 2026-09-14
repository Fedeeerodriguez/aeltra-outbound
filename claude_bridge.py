# -*- coding: utf-8 -*-
"""Puente a los agentes .md de Claude Code: los dispara en headless (claude -p --agent)."""
import json
import shutil
import subprocess

import config
import activity

CLAUDE_BIN = shutil.which("claude") or r"C:\Users\Usuario\AppData\Roaming\npm\claude.cmd"

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
    activity.update(slot, "trabajando", f"Claude Code · {agente} ejecutando…")
    try:
        proc = subprocess.run(
            [CLAUDE_BIN, "-p", objetivo, "--agent", agente,
             "--permission-mode", "bypassPermissions",
             "--output-format", "json", "--max-budget-usd", str(budget)],
            cwd=config.BASE_DIR, capture_output=True, text=True, timeout=timeout,
        )
        result = ""
        try:
            result = json.loads(proc.stdout).get("result", "")
        except Exception:
            result = (proc.stdout or "")[-1500:]
        ok = proc.returncode == 0
        activity.update(slot, "listo" if ok else "error",
                        f"Claude Code · {agente}: {'terminó ✅' if ok else 'falló'}")
        return {"ok": ok, "resultado": result,
                "error": (proc.stderr or "")[-500:] if not ok else None}
    except subprocess.TimeoutExpired:
        activity.update(slot, "error", f"Claude Code · {agente}: timeout")
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        activity.update(slot, "error", f"Claude Code · {agente}: {e}")
        return {"ok": False, "error": str(e)}
