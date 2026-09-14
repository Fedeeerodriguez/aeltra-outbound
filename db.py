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
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS plantillas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campania_id INTEGER,
    variante TEXT DEFAULT 'A',
    asunto TEXT,
    cuerpo TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS envios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contacto_id INTEGER,
    campania_id INTEGER,
    plantilla_id INTEGER,
    email TEXT,
    status TEXT DEFAULT 'queued',      -- queued | sent | failed | skipped
    scheduled_at TEXT,
    sent_at TEXT,
    message_id TEXT,
    error TEXT
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

CREATE INDEX IF NOT EXISTS idx_envios_due ON envios(status, scheduled_at);
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
    try:
        conn.execute("ALTER TABLE rutinas ADD COLUMN motor TEXT DEFAULT 'engine'")
    except Exception:
        pass
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("DB lista en", DB_PATH)
