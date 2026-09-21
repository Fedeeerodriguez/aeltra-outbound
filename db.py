# -*- coding: utf-8 -*-
"""SQLite: conexión + esquema del pipeline."""
import sqlite3
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS contactos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,
    email TEXT UNIQUE NOT NULL,
    empresa TEXT,
    nicho TEXT,
    pais TEXT,
    fuente TEXT,
    estado TEXT DEFAULT 'prospecto',
    notas TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS campanias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,
    objetivo TEXT,
    brief_json TEXT,
    estado TEXT DEFAULT 'borrador',
    cantidad_objetivo INTEGER,
    ventana_horas REAL,
    tipo TEXT DEFAULT 'simple',        -- simple | secuencia
    pasos_json TEXT,                   -- delays/config de la secuencia
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS plantillas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campania_id INTEGER,
    variante TEXT DEFAULT 'A',
    asunto TEXT,
    cuerpo TEXT,
    paso INTEGER DEFAULT 1,            -- 1 | 2 | 3 (paso de la secuencia)
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS envios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contacto_id INTEGER,
    campania_id INTEGER,
    plantilla_id INTEGER,
    email TEXT,
    status TEXT DEFAULT 'queued',      -- queued | sent | failed | skipped | cancelled
    scheduled_at TEXT,
    sent_at TEXT,
    message_id TEXT,
    error TEXT,
    paso INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS supresion (
    email TEXT PRIMARY KEY,
    motivo TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contacto_id INTEGER,
    tipo TEXT,
    payload TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rutinas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT,
    tipo TEXT,             -- 'busqueda' (solo recopila) | 'campania' (busca+escribe+envia)
    instruccion TEXT,      -- el texto que se le pasa al agente
    hora TEXT,             -- 'HH:MM' hora de disparo
    frecuencia TEXT DEFAULT 'diaria',
    motor TEXT DEFAULT 'engine',   -- 'engine' (Python) | 'claude' (agentes .md de Claude Code)
    activa INTEGER DEFAULT 1,
    ultimo_run TEXT,       -- 'YYYY-MM-DD' del último disparo (evita repetir el mismo día)
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agente_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agente TEXT,             -- orquestador | busqueda | copywriter | ejecutor
    accion TEXT,             -- qué se le pidió / qué hizo
    resultado TEXT,          -- resultado (texto largo)
    ok INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS kv (
    clave TEXT PRIMARY KEY,
    valor TEXT
);

CREATE INDEX IF NOT EXISTS idx_envios_due ON envios(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_hist_ag ON agente_historial(agente, id);
"""

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    # migración suave para bases viejas
    for stmt in (
        "ALTER TABLE rutinas ADD COLUMN motor TEXT DEFAULT 'engine'",
        "ALTER TABLE contactos ADD COLUMN estado_ts TEXT",   # cuándo cambió de estado
        "ALTER TABLE contactos ADD COLUMN campania_id INTEGER",
        # secuencia (drip 3 pasos) + detección de respuestas
        "ALTER TABLE plantillas ADD COLUMN paso INTEGER DEFAULT 1",
        "ALTER TABLE envios ADD COLUMN paso INTEGER DEFAULT 1",
        "ALTER TABLE campanias ADD COLUMN tipo TEXT DEFAULT 'simple'",   # simple | secuencia
        "ALTER TABLE campanias ADD COLUMN pasos_json TEXT",              # delays y config de pasos
    ):
        try:
            conn.execute(stmt)
        except Exception:
            pass
    # índice que depende de la columna 'paso' (después de las migraciones)
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_envios_seq ON envios(contacto_id, campania_id, paso)")
    except Exception:
        pass
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("DB lista en", DB_PATH)
