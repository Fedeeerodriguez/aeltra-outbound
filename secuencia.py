# -*- coding: utf-8 -*-
"""Motor de secuencia (drip) de Aeltra Outbound.

Una campaña 'secuencia' tiene hasta 3 plantillas (paso 1, 2, 3). El paso 1 lo encola
la creación de la campaña. Este motor se encarga de los FOLLOW-UPS condicionales:

  - Paso 2: se encola X horas después del paso 1, SOLO si el contacto no respondió.
  - Paso 3: se encola Y horas después del paso 2, SOLO si el contacto no respondió.
  - Tras el paso 3, si pasa el período de gracia sin respuesta → 'no_respondio'.

Si el contacto responde (lo detecta inbox.py por IMAP) pasa a 'respondio' y sale de
la secuencia automáticamente (deja de estar en estado 'enviado').
"""
import json
from datetime import datetime, timedelta

from db import get_conn

# Horas de espera ANTES de cada paso siguiente. delays[1] = espera antes del paso 2, etc.
DEFAULT_DELAYS = {2: 24.0, 3: 48.0}
GRACE_HORAS_FINAL = 72.0    # tras el paso 3 sin respuesta → 'no_respondio'


def _delays(camp_row):
    try:
        cfg = json.loads(camp_row["pasos_json"] or "{}")
        d = cfg.get("delays_horas")
        if isinstance(d, dict):
            return {2: float(d.get("2", 24)), 3: float(d.get("3", 48))}
        if isinstance(d, list) and len(d) >= 3:   # [paso1, delay2, delay3]
            return {2: float(d[1]), 3: float(d[2])}
    except Exception:
        pass
    return dict(DEFAULT_DELAYS)


def _parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace(" ", "T"))
    except Exception:
        return None


def avanzar():
    """Recorre las campañas de secuencia activas y encola el próximo paso donde corresponda.
    Devuelve cuántos envíos nuevos encoló."""
    conn = get_conn()
    ahora = datetime.utcnow()
    encolados = 0
    try:
        camps = conn.execute(
            "SELECT id,pasos_json FROM campanias WHERE tipo='secuencia' AND estado='activa'").fetchall()
        for camp in camps:
            cid = camp["id"]
            delays = _delays(camp)
            plantillas = {r["paso"]: r["id"] for r in conn.execute(
                "SELECT id,paso FROM plantillas WHERE campania_id=?", (cid,))}
            # Contactos que fueron contactados y todavía no respondieron (siguen 'enviado')
            contactos = conn.execute(
                "SELECT id,email FROM contactos WHERE campania_id=? AND estado='enviado'", (cid,)).fetchall()
            for c in contactos:
                fila = conn.execute(
                    "SELECT MAX(paso) AS mp FROM envios WHERE contacto_id=? AND campania_id=? AND status='sent'",
                    (c["id"], cid)).fetchone()
                n = fila["mp"] or 0
                if n <= 0:
                    continue   # todavía no salió ni el paso 1
                ultimo = conn.execute(
                    "SELECT sent_at FROM envios WHERE contacto_id=? AND campania_id=? AND paso=? "
                    "AND status='sent' ORDER BY id DESC LIMIT 1", (c["id"], cid, n)).fetchone()
                t_last = _parse_ts(ultimo["sent_at"]) if ultimo else None
                if not t_last:
                    continue

                if n < 3:
                    prox = n + 1
                    # ¿ya hay algo en cola o enviado para el próximo paso? no dupliques
                    ya = conn.execute(
                        "SELECT 1 FROM envios WHERE contacto_id=? AND campania_id=? AND paso=? "
                        "AND status IN ('queued','sent') LIMIT 1", (c["id"], cid, prox)).fetchone()
                    if ya:
                        continue
                    espera = delays.get(prox, 24.0)
                    if (ahora - t_last) >= timedelta(hours=espera):
                        pid = plantillas.get(prox)
                        if pid:
                            conn.execute(
                                "INSERT INTO envios (contacto_id,campania_id,plantilla_id,email,status,scheduled_at,paso) "
                                "VALUES (?,?,?,?, 'queued', ?, ?)",
                                (c["id"], cid, pid, c["email"], ahora.isoformat(timespec="seconds"), prox))
                            encolados += 1
                else:
                    # paso 3 ya enviado: si pasó la gracia sin respuesta → no_respondio
                    if (ahora - t_last) >= timedelta(hours=GRACE_HORAS_FINAL):
                        conn.execute(
                            "UPDATE contactos SET estado='no_respondio', estado_ts=datetime('now') WHERE id=?",
                            (c["id"],))
        conn.commit()
    finally:
        conn.close()
    return encolados
