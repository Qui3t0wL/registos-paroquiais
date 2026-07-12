import sqlite3
import os
from typing import Optional, Tuple, List
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "registos.db")


class Database:
    def __init__(self):
        self.path = DB_PATH
        self.criar_tabelas()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def criar_tabelas(self):
        conn = self._conn()
        cur = conn.cursor()

        # Tabela de uploads
        cur.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ficheiro    TEXT NOT NULL,
            tipo        TEXT NOT NULL,
            data_upload TEXT NOT NULL,
            registos    INTEGER DEFAULT 0,
            avisos      INTEGER DEFAULT 0
        )
        """)

        # Batismos
        cur.execute("""
        CREATE TABLE IF NOT EXISTS batismos (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id         INTEGER REFERENCES uploads(id),
            fonte             TEXT,
            fls               TEXT,
            ano               INTEGER,
            nr_ordem          TEXT,
            nome              TEXT,
            data_nasc         TEXT,
            local_nascimento  TEXT,
            pai               TEXT,
            mae               TEXT,
            avo_paterno       TEXT,
            avo_paterna       TEXT,
            avo_materno       TEXT,
            avo_materna       TEXT,
            notas             TEXT
        )
        """)

        # Casamentos
        cur.execute("""
        CREATE TABLE IF NOT EXISTS casamentos (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id         INTEGER REFERENCES uploads(id),
            fonte             TEXT,
            fls               TEXT,
            ano               INTEGER,
            nr_ordem          TEXT,
            data              TEXT,
            noivo             TEXT,
            idade_dnasc_noivo TEXT,
            nat_noivo         TEXT,
            noiva             TEXT,
            idade_dnasc_noiva TEXT,
            nat_noiva         TEXT,
            local             TEXT,
            pai_noivo         TEXT,
            nat_pai_noivo     TEXT,
            mae_noivo         TEXT,
            nat_mae_noivo     TEXT,
            pai_noiva         TEXT,
            nat_pai_noiva     TEXT,
            mae_noiva         TEXT,
            nat_mae_noiva     TEXT,
            testemunha1       TEXT,
            testemunha2       TEXT,
            notas             TEXT
        )
        """)

        # Óbitos
        cur.execute("""
        CREATE TABLE IF NOT EXISTS obitos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id   INTEGER REFERENCES uploads(id),
            fonte       TEXT,
            fls         TEXT,
            ano         INTEGER,
            nr_ordem    TEXT,
            nome        TEXT,
            data_obito  TEXT,
            local       TEXT,
            pai         TEXT,
            mae         TEXT,
            notas       TEXT
        )
        """)

        # Índices para pesquisa
        for tabela, campo in [
            ("batismos", "nome"), ("batismos", "ano"),
            ("batismos", "pai"), ("batismos", "mae"),
            ("casamentos", "noivo"), ("casamentos", "noiva"), ("casamentos", "ano"),
            ("obitos", "nome"), ("obitos", "ano"),
        ]:
            cur.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{tabela}_{campo}
            ON {tabela} ({campo} COLLATE NOCASE)
            """)

        conn.commit()
        conn.close()

    # ── Pesquisa unificada ────────────────────────────────────────────────────

    def pesquisar(
        self, q: Optional[str], tipo: Optional[str],
        ano_min: Optional[int], ano_max: Optional[int],
        fonte: Optional[str], pagina: int, por_pagina: int
    ) -> Tuple[List[dict], int]:

        tipos = ["batismo", "casamento", "obito"] if not tipo else [tipo]
        todos = []

        for t in tipos:
            rows = self._pesquisar_tabela(t, q, ano_min, ano_max, fonte)
            todos.extend(rows)

        # Ordenar por ano desc, depois nome
        todos.sort(key=lambda r: ((r.get("ano") or 0), r.get("_nome_sort", "")))

        total = len(todos)
        inicio = (pagina - 1) * por_pagina
        return todos[inicio:inicio + por_pagina], total

    def _pesquisar_tabela(self, tipo: str, q, ano_min, ano_max, fonte) -> List[dict]:
        conn = self._conn()
        cur = conn.cursor()

        if tipo == "batismo":
            tabela = "batismos"
            campos_nome = ["nome", "pai", "mae", "avo_paterno", "avo_paterna",
                           "avo_materno", "avo_materna"]
            select = """
                SELECT id, 'batismo' as tipo, fonte, ano, nome,
                       data_nasc as data, local_nascimento as local,
                       pai, mae, notas,
                       nome as _nome_sort
                FROM batismos
            """
        elif tipo == "casamento":
            tabela = "casamentos"
            campos_nome = ["noivo", "noiva", "pai_noivo", "mae_noivo",
                           "pai_noiva", "mae_noiva", "testemunha1", "testemunha2"]
            select = """
                SELECT id, 'casamento' as tipo, fonte, ano,
                       (noivo || ' & ' || noiva) as nome,
                       data, local, pai_noivo as pai, mae_noivo as mae, notas,
                       noivo as _nome_sort
                FROM casamentos
            """
        else:
            tabela = "obitos"
            campos_nome = ["nome", "pai", "mae"]
            select = """
                SELECT id, 'obito' as tipo, fonte, ano, nome,
                       data_obito as data, local,
                       pai, mae, notas,
                       nome as _nome_sort
                FROM obitos
            """

        where = []
        params = []

        if q:
            termos = q.strip().split()
            for termo in termos:
                condicoes = " OR ".join(
                    [f"{c} LIKE ? COLLATE NOCASE" for c in campos_nome]
                )
                where.append(f"({condicoes})")
                params.extend([f"%{termo}%"] * len(campos_nome))

        if ano_min:
            where.append("ano >= ?")
            params.append(ano_min)
        if ano_max:
            where.append("ano <= ?")
            params.append(ano_max)
        if fonte:
            where.append("fonte LIKE ?")
            params.append(f"%{fonte}%")

        sql = select
        if where:
            sql += " WHERE " + " AND ".join(where)

        cur.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def obter_registo(self, tipo: str, id: int) -> Optional[dict]:
        tabela = {"batismo": "batismos", "casamento": "casamentos", "obito": "obitos"}[tipo]
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None

    # ── Estatísticas ──────────────────────────────────────────────────────────

    def estatisticas(self) -> dict:
        conn = self._conn()
        cur = conn.cursor()
        stats = {}
        for nome, tabela in [("batismos", "batismos"), ("casamentos", "casamentos"), ("obitos", "obitos")]:
            cur.execute(f"SELECT COUNT(*) as total, MIN(ano) as ano_min, MAX(ano) as ano_max FROM {tabela}")
            row = dict(cur.fetchone())
            stats[nome] = row
        conn.close()
        return stats

    def estatisticas_detalhadas(self) -> dict:
        conn = self._conn()
        cur = conn.cursor()
        resultado = {}
        for nome, tabela, campo_data in [
            ("batismos_por_decada",    "batismos",   "ano"),
            ("casamentos_por_decada",  "casamentos", "ano"),
            ("obitos_por_decada",      "obitos",     "ano"),
        ]:
            cur.execute(f"""
                SELECT (ano / 10) * 10 as decada, COUNT(*) as total
                FROM {tabela}
                WHERE ano IS NOT NULL
                GROUP BY decada
                ORDER BY decada
            """)
            resultado[nome] = [{"decada": r[0], "total": r[1]} for r in cur.fetchall()]
        conn.close()
        return resultado

    def listar_fontes(self) -> List[str]:
        conn = self._conn()
        cur = conn.cursor()
        fontes = set()
        for tabela in ("batismos", "casamentos", "obitos"):
            cur.execute(f"SELECT DISTINCT fonte FROM {tabela} WHERE fonte IS NOT NULL")
            fontes.update(r[0] for r in cur.fetchall() if r[0])
        conn.close()
        return sorted(fontes)

    def listar_uploads(self) -> List[dict]:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM uploads ORDER BY data_upload DESC")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    # ── Inserção de registos ──────────────────────────────────────────────────

    def inserir_batismos(self, registos: List[dict], upload_id: int):
        conn = self._conn()
        cur = conn.cursor()
        campos = ['fonte','fls','ano','nr_ordem','nome','data_nasc',
                  'local_nascimento','pai','mae','avo_paterno','avo_paterna',
                  'avo_materno','avo_materna','notas']
        cur.executemany("""
            INSERT INTO batismos
            (upload_id, fonte, fls, ano, nr_ordem, nome, data_nasc,
             local_nascimento, pai, mae, avo_paterno, avo_paterna,
             avo_materno, avo_materna, notas)
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (upload_id, *[r.get(c) for c in campos])
            for r in registos
        ])
        conn.commit()
        conn.close()
    
    def inserir_casamentos(self, registos: List[dict], upload_id: int):
        conn = self._conn()
        cur = conn.cursor()
        campos = ['fonte','fls','ano','nr_ordem','data','noivo',
                  'idade_dnasc_noivo','nat_noivo','noiva','idade_dnasc_noiva','nat_noiva',
                  'local','pai_noivo','nat_pai_noivo','mae_noivo','nat_mae_noivo',
                  'pai_noiva','nat_pai_noiva','mae_noiva','nat_mae_noiva',
                  'testemunha1','testemunha2','notas']
        cur.executemany("""
            INSERT INTO casamentos
            (upload_id, fonte, fls, ano, nr_ordem, data, noivo,
             idade_dnasc_noivo, nat_noivo, noiva, idade_dnasc_noiva, nat_noiva,
             local, pai_noivo, nat_pai_noivo, mae_noivo, nat_mae_noivo,
             pai_noiva, nat_pai_noiva, mae_noiva, nat_mae_noiva,
             testemunha1, testemunha2, notas)
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (upload_id, *[r.get(c) for c in campos])
            for r in registos
        ])
        conn.commit()
        conn.close()

    def inserir_obitos(self, registos: List[dict], upload_id: int):
        conn = self._conn()
        cur = conn.cursor()
        campos = ['fonte','fls','ano','nr_ordem','nome','data_obito','local','pai','mae','notas']
        cur.executemany("""
            INSERT INTO obitos
            (upload_id, fonte, fls, ano, nr_ordem, nome, data_obito,
             local, pai, mae, notas)
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (upload_id, *[r.get(c) for c in campos])
            for r in registos
        ])
        conn.commit()
        conn.close()

    def criar_upload(self, ficheiro: str, tipo: str, registos: int, avisos: int) -> int:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO uploads (ficheiro, tipo, data_upload, registos, avisos)
            VALUES (?, ?, ?, ?, ?)
        """, (ficheiro, tipo, datetime.now().isoformat(timespec="seconds"), registos, avisos))
        upload_id = cur.lastrowid
        conn.commit()
        conn.close()
        return upload_id
