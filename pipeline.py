# -*- coding: utf-8 -*-
"""Operaciones sobre el pipeline (contactos, campañas, plantillas, envíos, supresión)."""
import json
from datetime import datetime
from db import get_conn

# ── Contactos ──
def add_contact(nombre, email, empresa=None, nicho=None, pais=None, fuente=None, estado="prospecto"):
    email = (email or "").strip().lower()
    if not email:
        return None
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO contactos (nombre,email,empresa,nicho,pais,fuente,estado)
               VALUES (?,?,?,?,?,?,?)""",
            (nombre, email, empresa, nicho, pais, fuente, estado),
        )
        conn.commit()
        return cur.lastrowid
    except Exception:
        # ya existe (email UNIQUE) → devolver el id existente
        row = conn.execute("SELECT id FROM contactos WHERE email=?", (email,)).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()

def find_contact_by_email(email):
    conn = get_conn()
    row = conn.execute("SELECT * FROM contactos WHERE email=?", ((email or "").strip().lower(),)).fetchone()
    conn.close()
    return dict(row) if row else None

def list_contacts(estado=None, limit=500):
    conn = get_conn()
    if estado:
        rows = conn.execute("SELECT * FROM contactos WHERE estado=? ORDER BY id DESC LIMIT ?", (estado, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM contactos ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_estado(contacto_id, estado):
    conn = get_conn()
    conn.execute("UPDATE contactos SET estado=? WHERE id=?", (estado, contacto_id))
    conn.commit()
    conn.close()

# ── Campañas / plantillas ──
def create_campania(nombre, objetivo, brief, cantidad_objetivo, ventana_horas):
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO campanias (nombre,objetivo,brief_json,estado,cantidad_objetivo,ventana_horas)
           VALUES (?,?,?, 'activa', ?, ?)""",
        (nombre, objetivo, json.dumps(brief, ensure_ascii=False), cantidad_objetivo, ventana_horas),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid

def set_campania_estado(campania_id, estado):
    conn = get_conn()
    conn.execute("UPDATE campanias SET estado=? WHERE id=?", (estado, campania_id))
    conn.commit()
    conn.close()

def create_plantilla(campania_id, asunto, cuerpo, variante="A"):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO plantillas (campania_id,variante,asunto,cuerpo) VALUES (?,?,?,?)",
        (campania_id, variante, asunto, cuerpo),
    )
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid

# ── Envíos (cola paceada) ──
def enqueue_envio(contacto_id, campania_id, plantilla_id, email, scheduled_at):
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO envios (contacto_id,campania_id,plantilla_id,email,status,scheduled_at)
           VALUES (?,?,?,?, 'queued', ?)""",
        (contacto_id, campania_id, plantilla_id, email, scheduled_at),
    )
    conn.commit()
    eid = cur.lastrowid
    conn.close()
    return eid

def due_envios(now_iso, limit=25):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM envios WHERE status='queued' AND scheduled_at<=? ORDER BY scheduled_at LIMIT ?",
        (now_iso, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mark_envio(envio_id, status, message_id=None, error=None):
    conn = get_conn()
    conn.execute(
        "UPDATE envios SET status=?, sent_at=?, message_id=?, error=? WHERE id=?",
        (status, datetime.utcnow().isoformat(timespec="seconds"), message_id, error, envio_id),
    )
    conn.commit()
    conn.close()

# ── Supresión (opt-out) ──
def add_supresion(email, motivo="baja"):
    email = (email or "").strip().lower()
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO supresion (email,motivo) VALUES (?,?)", (email, motivo))
    conn.commit()
    conn.close()

def is_suppressed(email):
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM supresion WHERE email=?", ((email or "").strip().lower(),)).fetchone()
    conn.close()
    return row is not None

# ── Eventos ──
def add_evento(contacto_id, tipo, payload=None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO eventos (contacto_id,tipo,payload) VALUES (?,?,?)",
        (contacto_id, tipo, json.dumps(payload, ensure_ascii=False) if payload else None),
    )
    conn.commit()
    conn.close()

# ── Métricas ──
def stats():
    conn = get_conn()
    def one(q, *a):
        r = conn.execute(q, a).fetchone()
        return r[0] if r else 0
    data = {
        "contactos": one("SELECT COUNT(*) FROM contactos"),
        "prospectos": one("SELECT COUNT(*) FROM contactos WHERE estado='prospecto'"),
        "contactados": one("SELECT COUNT(*) FROM contactos WHERE estado='contactado'"),
        "respondieron": one("SELECT COUNT(*) FROM contactos WHERE estado='respondió'"),
        "clientes": one("SELECT COUNT(*) FROM contactos WHERE estado='cliente'"),
        "enviados": one("SELECT COUNT(*) FROM envios WHERE status='sent'"),
        "en_cola": one("SELECT COUNT(*) FROM envios WHERE status='queued'"),
        "fallidos": one("SELECT COUNT(*) FROM envios WHERE status='failed'"),
        "supresion": one("SELECT COUNT(*) FROM supresion"),
        "campanias": one("SELECT COUNT(*) FROM campanias"),
    }
    conn.close()
    return data


# ── Historial de agentes (persistente) ──
def log_agente(agente, accion, resultado="", ok=True):
    conn = get_conn()
    conn.execute("INSERT INTO agente_historial (agente,accion,resultado,ok) VALUES (?,?,?,?)",
                 (agente, (accion or "")[:400], (resultado or "")[:4000], 1 if ok else 0))
    conn.commit()
    conn.close()

def historial_agente(agente, limit=40):
    conn = get_conn()
    rows = conn.execute("SELECT accion,resultado,ok,created_at FROM agente_historial "
                        "WHERE agente=? ORDER BY id DESC LIMIT ?", (agente, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Pipeline (estados de cliente) ──
PIPELINE_ESTADOS = ["prospecto", "enviado", "respondio", "no_respondio",
                    "seguimiento", "reunion", "cerrado", "perdido"]

def mover_contacto(cid, estado):
    conn = get_conn()
    conn.execute("UPDATE contactos SET estado=?, estado_ts=datetime('now') WHERE id=?", (estado, cid))
    conn.commit()
    conn.close()

def marcar_enviado(contacto_id):
    conn = get_conn()
    conn.execute("UPDATE contactos SET estado='enviado', estado_ts=datetime('now') "
                 "WHERE id=? AND estado IN ('prospecto','contactado')", (contacto_id,))
    conn.commit()
    conn.close()

def contactos_pipeline():
    conn = get_conn()
    rows = conn.execute("SELECT id,nombre,email,empresa,nicho,estado,estado_ts,campania_id "
                        "FROM contactos ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def metricas():
    conn = get_conn()
    def scalar(q, *a):
        r = conn.execute(q, a).fetchone()
        return (list(r)[0] if r else 0) or 0
    por_estado = {row["estado"]: row["n"] for row in
                  conn.execute("SELECT estado,COUNT(*) n FROM contactos GROUP BY estado")}
    camps = []
    for c in conn.execute("SELECT id,nombre,objetivo,estado FROM campanias ORDER BY id DESC"):
        cid = c["id"]
        env = scalar("SELECT COUNT(*) FROM envios WHERE campania_id=? AND status='sent'", cid)
        cola = scalar("SELECT COUNT(*) FROM envios WHERE campania_id=? AND status='queued'", cid)
        exitos = scalar("SELECT COUNT(*) FROM contactos WHERE campania_id=? "
                        "AND estado IN ('respondio','reunion','cerrado')", cid)
        camps.append({"id": cid, "nombre": c["nombre"], "objetivo": c["objetivo"], "estado": c["estado"],
                      "enviados": env, "en_cola": cola, "exitos": exitos,
                      "tasa": (round(100 * exitos / env, 1) if env else 0)})
    data = {
        "total_contactos": scalar("SELECT COUNT(*) FROM contactos"),
        "por_estado": por_estado,
        "respondio": por_estado.get("respondio", 0) + por_estado.get("reunion", 0) + por_estado.get("cerrado", 0),
        "reuniones": por_estado.get("reunion", 0),
        "clientes": por_estado.get("cerrado", 0),
        "enviados": scalar("SELECT COUNT(*) FROM envios WHERE status='sent'"),
        "campanias": camps,
    }
    conn.close()
    return data

def auto_no_respondio(dias_habiles=3):
    """Mueve contactos 'enviado' sin respuesta a 'no_respondio' tras N días hábiles."""
    from datetime import timedelta
    conn = get_conn()
    movidos = 0
    hoy = datetime.utcnow().date()
    for r in conn.execute("SELECT id,estado_ts FROM contactos WHERE estado='enviado'").fetchall():
        ts = r["estado_ts"]
        if not ts:
            continue
        try:
            base = datetime.fromisoformat(ts.replace(" ", "T")).date()
        except Exception:
            continue
        habiles, cur = 0, base
        while cur < hoy:
            cur = cur + timedelta(days=1)
            if cur.weekday() < 5:
                habiles += 1
        if habiles >= dias_habiles:
            conn.execute("UPDATE contactos SET estado='no_respondio', estado_ts=datetime('now') WHERE id=?", (r["id"],))
            movidos += 1
    conn.commit()
    conn.close()
    return movidos
