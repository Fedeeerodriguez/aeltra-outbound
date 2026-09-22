# -*- coding: utf-8 -*-
"""Conexión + esquema del pipeline.

Por defecto usa **SQLite** (archivo local). Si está seteada la variable de entorno
**DATABASE_URL** (postgres://…, ej. Supabase), usa **Postgres**. El resto del código
sigue usando siempre placeholders '?', filas accesibles por índice y por clave, y
`cur.lastrowid`: acá se traduce a Postgres de forma transparente.
"""
import os
import re
import sqlite3
from config import DB_PATH

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
IS_PG = DATABASE_URL.startswith("postgres")

# ── Esquema SQLite ──
SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS contactos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT, email TEXT UNIQUE NOT NULL, empresa TEXT, nicho TEXT, pais TEXT,
    fuente TEXT, estado TEXT DEFAULT 'prospecto', notas TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS campanias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT, objetivo TEXT, brief_json TEXT, estado TEXT DEFAULT 'borrador',
    cantidad_objetivo INTEGER, ventana_horas REAL,
    tipo TEXT DEFAULT 'simple', pasos_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS plantillas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campania_id INTEGER, variante TEXT DEFAULT 'A', asunto TEXT, cuerpo TEXT,
    paso INTEGER DEFAULT 1, created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS envios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contacto_id INTEGER, campania_id INTEGER, plantilla_id INTEGER, email TEXT,
    status TEXT DEFAULT 'queued', scheduled_at TEXT, sent_at TEXT,
    message_id TEXT, error TEXT, paso INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS supresion (
    email TEXT PRIMARY KEY, motivo TEXT, created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contacto_id INTEGER, tipo TEXT, payload TEXT, created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS rutinas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT, tipo TEXT, instruccion TEXT, hora TEXT, frecuencia TEXT DEFAULT 'diaria',
    motor TEXT DEFAULT 'engine', activa INTEGER DEFAULT 1, ultimo_run TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS agente_historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agente TEXT, accion TEXT, resultado TEXT, ok INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS kv (clave TEXT PRIMARY KEY, valor TEXT);
CREATE INDEX IF NOT EXISTS idx_envios_due ON envios(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_hist_ag ON agente_historial(agente, id);
"""

# ── Esquema Postgres (BIGSERIAL, timestamps como texto para no cambiar la app) ──
_NOW_PG = "to_char((now() at time zone 'utc'),'YYYY-MM-DD HH24:MI:SS')"
SCHEMA_PG = f"""
CREATE TABLE IF NOT EXISTS contactos (
  id BIGSERIAL PRIMARY KEY, nombre TEXT, email TEXT UNIQUE NOT NULL, empresa TEXT,
  nicho TEXT, pais TEXT, fuente TEXT, estado TEXT DEFAULT 'prospecto', notas TEXT,
  estado_ts TEXT, campania_id BIGINT, created_at TEXT DEFAULT {_NOW_PG}
);
CREATE TABLE IF NOT EXISTS campanias (
  id BIGSERIAL PRIMARY KEY, nombre TEXT, objetivo TEXT, brief_json TEXT,
  estado TEXT DEFAULT 'borrador', cantidad_objetivo INTEGER, ventana_horas DOUBLE PRECISION,
  tipo TEXT DEFAULT 'simple', pasos_json TEXT, created_at TEXT DEFAULT {_NOW_PG}
);
CREATE TABLE IF NOT EXISTS plantillas (
  id BIGSERIAL PRIMARY KEY, campania_id BIGINT, variante TEXT DEFAULT 'A',
  asunto TEXT, cuerpo TEXT, paso INTEGER DEFAULT 1, created_at TEXT DEFAULT {_NOW_PG}
);
CREATE TABLE IF NOT EXISTS envios (
  id BIGSERIAL PRIMARY KEY, contacto_id BIGINT, campania_id BIGINT, plantilla_id BIGINT,
  email TEXT, status TEXT DEFAULT 'queued', scheduled_at TEXT, sent_at TEXT,
  message_id TEXT, error TEXT, paso INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS supresion (
  email TEXT PRIMARY KEY, motivo TEXT, created_at TEXT DEFAULT {_NOW_PG}
);
CREATE TABLE IF NOT EXISTS eventos (
  id BIGSERIAL PRIMARY KEY, contacto_id BIGINT, tipo TEXT, payload TEXT,
  created_at TEXT DEFAULT {_NOW_PG}
);
CREATE TABLE IF NOT EXISTS rutinas (
  id BIGSERIAL PRIMARY KEY, nombre TEXT, tipo TEXT, instruccion TEXT, hora TEXT,
  frecuencia TEXT DEFAULT 'diaria', motor TEXT DEFAULT 'engine', activa INTEGER DEFAULT 1,
  ultimo_run TEXT, created_at TEXT DEFAULT {_NOW_PG}
);
CREATE TABLE IF NOT EXISTS agente_historial (
  id BIGSERIAL PRIMARY KEY, agente TEXT, accion TEXT, resultado TEXT, ok INTEGER DEFAULT 1,
  created_at TEXT DEFAULT {_NOW_PG}
);
CREATE TABLE IF NOT EXISTS kv (clave TEXT PRIMARY KEY, valor TEXT);
CREATE INDEX IF NOT EXISTS idx_envios_due ON envios(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_hist_ag ON agente_historial(agente, id);
CREATE INDEX IF NOT EXISTS idx_envios_seq ON envios(contacto_id, campania_id, paso);
"""

# ── Capa de compatibilidad Postgres ──
_ID_TABLES = {"contactos", "campanias", "plantillas", "envios", "eventos", "rutinas", "agente_historial"}

def _prep(sql):
    """Traduce SQL SQLite → Postgres: placeholders y datetime('now')."""
    sql = sql.replace("?", "%s")
    sql = sql.replace("datetime('now')", _NOW_PG)
    return sql

def _needs_returning(sql_low):
    if not sql_low.startswith("insert into") or "returning" in sql_low:
        return False
    m = re.match(r"insert\s+into\s+([a-z_]+)", sql_low)
    return bool(m and m.group(1) in _ID_TABLES)

class _Row:
    """Fila accesible por índice y por clave, y convertible a dict (como sqlite3.Row)."""
    __slots__ = ("_cols", "_vals", "_map")
    def __init__(self, cols, vals):
        self._cols = cols; self._vals = vals; self._map = dict(zip(cols, vals))
    def __getitem__(self, k):
        return self._vals[k] if isinstance(k, int) else self._map[k]
    def keys(self): return list(self._cols)
    def get(self, k, d=None): return self._map.get(k, d)
    def __iter__(self): return iter(self._vals)
    def __len__(self): return len(self._vals)

class _Cur:
    def __init__(self, cur):
        self._cur = cur
        self.lastrowid = None
        self.rowcount = cur.rowcount
    def _cols(self):
        return [d[0] for d in (self._cur.description or [])]
    def fetchone(self):
        r = self._cur.fetchone()
        return _Row(self._cols(), r) if r is not None else None
    def fetchall(self):
        cols = self._cols()
        return [_Row(cols, r) for r in self._cur.fetchall()]
    def __iter__(self):
        cols = self._cols()
        for r in self._cur:
            yield _Row(cols, r)

class _PgConn:
    """Envuelve psycopg2 con la misma interfaz que usamos de sqlite3."""
    def __init__(self):
        import psycopg2
        self._c = psycopg2.connect(DATABASE_URL, connect_timeout=20)
    def execute(self, sql, params=()):
        s = _prep(sql)
        low = s.lstrip().lower()
        ret = _needs_returning(low)
        if ret:
            s = s.rstrip().rstrip(";") + " RETURNING id"
        cur = self._c.cursor()
        cur.execute(s, tuple(params) if params else None)
        w = _Cur(cur)
        if ret:
            try:
                row = cur.fetchone()
                w.lastrowid = row[0] if row else None
            except Exception:
                w.lastrowid = None
        return w
    def executemany(self, sql, seq):
        cur = self._c.cursor()
        cur.executemany(_prep(sql), list(seq))
        return _Cur(cur)
    def executescript(self, script):
        cur = self._c.cursor()
        cur.execute(script)
        return _Cur(cur)
    def commit(self): self._c.commit()
    def close(self):
        try: self._c.close()
        except Exception: pass


def get_conn():
    if IS_PG:
        return _PgConn()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    conn = get_conn()
    if IS_PG:
        conn.executescript(SCHEMA_PG)
        conn.commit(); conn.close()
        return
    conn.executescript(SCHEMA_SQLITE)
    # migración suave para bases SQLite viejas
    for stmt in (
        "ALTER TABLE rutinas ADD COLUMN motor TEXT DEFAULT 'engine'",
        "ALTER TABLE contactos ADD COLUMN estado_ts TEXT",
        "ALTER TABLE contactos ADD COLUMN campania_id INTEGER",
        "ALTER TABLE plantillas ADD COLUMN paso INTEGER DEFAULT 1",
        "ALTER TABLE envios ADD COLUMN paso INTEGER DEFAULT 1",
        "ALTER TABLE campanias ADD COLUMN tipo TEXT DEFAULT 'simple'",
        "ALTER TABLE campanias ADD COLUMN pasos_json TEXT",
    ):
        try:
            conn.execute(stmt)
        except Exception:
            pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_envios_seq ON envios(contacto_id, campania_id, paso)")
    except Exception:
        pass
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("DB lista ·", "Postgres" if IS_PG else f"SQLite ({DB_PATH})")
