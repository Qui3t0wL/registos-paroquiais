import sqlite3
import os
import re
import unicodedata
import uuid
from typing import Optional, Tuple, List
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "registos.db")

def _calcular_relevancia(reg, q):
    """Devolve score de relevância: menor = mais relevante."""
    if not q:
        return 0
    termos = q.strip().split()
    termos_norm = [_normalizar(t) for t in termos]
    padrao_ordenado = ".*".join(re.escape(t) for t in termos_norm)
    nome_raw = reg.get("nome") or reg.get("_nome_sort") or ""
    nome = _normalizar(nome_raw)
    q_norm = _normalizar(q.strip())

    # Frase exacta
    if q_norm in nome:
        return 0
    # Tokens pela ordem (com palavras no meio)
    if re.search(padrao_ordenado, nome, re.IGNORECASE):
        return 1
    # Todos os termos presentes em qualquer ordem
    if all(t in nome for t in termos_norm):
        return 2
    return 3

def _normalizar(texto):
    """Remove acentos para pesquisa insensível a acentos."""
    if texto is None:
        return None
    return unicodedata.normalize('NFD', texto).encode('ascii', 'ignore').decode('ascii').lower()
    
class Database:
    def __init__(self):
        self.path = DB_PATH
        self.criar_tabelas()

    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # Registar função de normalização
        conn.create_function("NORMALIZAR", 1, _normalizar)
        return conn

    def criar_tabelas(self):
        conn = self._conn()
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS uploads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ficheiro    TEXT NOT NULL,
            tipo        TEXT NOT NULL,
            freguesia   TEXT,
            codigo_adist TEXT,
            data_upload TEXT NOT NULL,
            registos    INTEGER DEFAULT 0,
            avisos      INTEGER DEFAULT 0,
			substitui_upload_id INTEGER
        )
        """)

        # Tabela de auditoria
        cur.execute("""
        CREATE TABLE IF NOT EXISTS auditoria (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            data        TEXT NOT NULL,
            ip          TEXT NOT NULL,
            endpoint    TEXT NOT NULL,
            metodo      TEXT NOT NULL,
            status      INTEGER,
            user_agent  TEXT
        )
        """)
        
        # Índice para queries de auditoria
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_auditoria_data
        ON auditoria (data)
        """)
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_auditoria_ip
        ON auditoria (ip)
        """)

		# Configurações da instância
        cur.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave   TEXT PRIMARY KEY,
            valor   TEXT NOT NULL
        )
        """)

        # Footer por defeito — só inserido se ainda não existir
        cur.execute("""
            INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (
                'footer_texto',
                'Exclusão de responsabilidade: A informação disponível nesta plataforma foi recolhida a partir de registos paroquiais disponíveis online em https://digitarq.arquivos.pt/. É possível que existam eventuais erros de transcrição.'
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
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id           INTEGER REFERENCES uploads(id),
            fonte               TEXT,
            fls                 TEXT,
            ano                 INTEGER,
            nr_ordem            TEXT,
            data                TEXT,
            noivo               TEXT,
            idade_dnasc_noivo   TEXT,
            nat_noivo           TEXT,
            noiva               TEXT,
            idade_dnasc_noiva   TEXT,
            nat_noiva           TEXT,
            residencia          TEXT,
            pai_noivo           TEXT,
            nat_pai_noivo       TEXT,
            mae_noivo           TEXT,
            nat_mae_noivo       TEXT,
            pai_noiva           TEXT,
            nat_pai_noiva       TEXT,
            mae_noiva           TEXT,
            nat_mae_noiva       TEXT,
            avo_paterno_noivo   TEXT,
            avo_paterna_noivo   TEXT,
            avo_materno_noivo   TEXT,
            avo_materna_noivo   TEXT,
            avo_paterno_noiva   TEXT,
            avo_paterna_noiva   TEXT,
            avo_materno_noiva   TEXT,
            avo_materna_noiva   TEXT,
            testemunha1         TEXT,
            testemunha2         TEXT,
            notas               TEXT
        )
        """)
        
        # Óbitos
        cur.execute("""
        CREATE TABLE IF NOT EXISTS obitos (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id         INTEGER REFERENCES uploads(id),
            fonte             TEXT,
            fls               TEXT,
            ano               INTEGER,
            nr_ordem          TEXT,
            nome              TEXT,
            data_obito        TEXT,
            local_falecimento TEXT,
            idade             TEXT,
            pai               TEXT,
            nat_pai           TEXT,
            mae               TEXT,
            nat_mae           TEXT,
            notas             TEXT
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
        self._criar_tabelas_federacao()

	# ── Configurações ─────────────────────────────────────────────────────────

    def obter_configuracao(self, chave: str) -> Optional[str]:
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None

    def definir_configuracao(self, chave: str, valor: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
            (chave, valor)
        )
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
        q_sort = q or ""
        todos.sort(key=lambda r: (_calcular_relevancia(r, q_sort),(r.get("ano") or 0)))

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
                       data, residencia as local, pai_noivo as pai, mae_noivo as mae, notas,
                       noivo as _nome_sort
                FROM casamentos
            """
        else:
            tabela = "obitos"
            campos_nome = ["nome", "pai", "mae"]
            select = """
                SELECT id, 'obito' as tipo, fonte, ano, nome,
                       data_obito as data, local_falecimento as local,
                       pai, mae, notas,
                       nome as _nome_sort
                FROM obitos
            """

        where = []
        params = []

        if q:
            termos = q.strip().split()
            # Normalizar os termos de pesquisa
            termos_norm = [_normalizar(t) for t in termos]
        
            if len(termos) == 1:
                # Palavra única — pesquisa normal
                condicoes = " OR ".join([f"NORMALIZAR({c}) LIKE ?" for c in campos_nome])
                where.append(f"({condicoes})")
                params.extend([f"%{termos_norm[0]}%"] * len(campos_nome))
        
            else:
                # Frase composta normalizada — três níveis de correspondência por prioridade:
	            # Nível 1: frase exacta ("José Alves")
                frase_norm = _normalizar(q.strip())
                cond_exacta = " OR ".join([f"NORMALIZAR({c}) LIKE ?" for c in campos_nome])
                params_exacta = [f"%{frase_norm}%"] * len(campos_nome)
        
                # Nível 2: tokens normalizados pela ordem com palavras no meio
	            # "José Alves" → LIKE '%José%Alves%'
                padrao_ordenado = "%" + "%".join(termos_norm) + "%"
                cond_ordenada = " OR ".join([f"NORMALIZAR({c}) LIKE ?" for c in campos_nome])
                params_ordenada = [padrao_ordenado] * len(campos_nome)
        
                # Nível 3: todos os termos presentes em qualquer ordem
            	# "José Alves" → contém "José" E contém "Alves"
                conds_termos = []
                params_termos = []
                for termo_norm in termos_norm:
                    cond_termo = " OR ".join([f"NORMALIZAR({c}) LIKE ?" for c in campos_nome])
                    conds_termos.append(f"({cond_termo})")
                    params_termos.extend([f"%{termo_norm}%"] * len(campos_nome))
        
                where.append(
                    f"(({cond_exacta}) OR ({cond_ordenada}) OR ({' AND '.join(conds_termos)}))"
                )
                params = params_exacta + params_ordenada + params_termos + params

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
        campos = [
            'fonte','fls','ano','nr_ordem','data','noivo',
            'idade_dnasc_noivo','nat_noivo','noiva','idade_dnasc_noiva','nat_noiva',
            'residencia','pai_noivo','nat_pai_noivo','mae_noivo','nat_mae_noivo',
            'pai_noiva','nat_pai_noiva','mae_noiva','nat_mae_noiva',
            'avo_paterno_noivo','avo_paterna_noivo','avo_materno_noivo','avo_materna_noivo',
            'avo_paterno_noiva','avo_paterna_noiva','avo_materno_noiva','avo_materna_noiva',
            'testemunha1','testemunha2','notas'
        ]
        cur.executemany("""
            INSERT INTO casamentos
            (upload_id, fonte, fls, ano, nr_ordem, data, noivo,
             idade_dnasc_noivo, nat_noivo, noiva, idade_dnasc_noiva, nat_noiva,
             residencia, pai_noivo, nat_pai_noivo, mae_noivo, nat_mae_noivo,
             pai_noiva, nat_pai_noiva, mae_noiva, nat_mae_noiva,
             avo_paterno_noivo, avo_paterna_noivo, avo_materno_noivo, avo_materna_noivo,
             avo_paterno_noiva, avo_paterna_noiva, avo_materno_noiva, avo_materna_noiva,
             testemunha1, testemunha2, notas)
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
             ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (upload_id, *[r.get(c) for c in campos])
            for r in registos
        ])
        conn.commit()
        conn.close()
    
    def inserir_obitos(self, registos: List[dict], upload_id: int):
        conn = self._conn()
        cur = conn.cursor()
        campos = [
            'fonte','fls','ano','nr_ordem','nome','data_obito',
            'local_falecimento','idade','pai','nat_pai','mae','nat_mae','notas'
        ]
        cur.executemany("""
            INSERT INTO obitos
            (upload_id, fonte, fls, ano, nr_ordem, nome, data_obito,
             local_falecimento, idade, pai, nat_pai, mae, nat_mae, notas)
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (upload_id, *[r.get(c) for c in campos])
            for r in registos
        ])
        conn.commit()
        conn.close()

    def criar_upload(self, ficheiro: str, tipo: str, registos: int,
	                 avisos: int, freguesia: str = None,
	                 substitui_upload_id: int = None) -> int:
	    conn = self._conn()
	    cur = conn.cursor()
	    cur.execute("""
	        INSERT INTO uploads (ficheiro, tipo, freguesia, data_upload, registos, avisos, substitui_upload_id)
	        VALUES (?, ?, ?, ?, ?, ?, ?)
	    """, (ficheiro, tipo, freguesia,
	          datetime.now().isoformat(timespec="seconds"), registos, avisos, substitui_upload_id))
	    upload_id = cur.lastrowid
	    conn.commit()
	    conn.close()
	    return upload_id

    def actualizar_registo_por_ref(self, tipo: str, fonte: str, nr_ordem: str, reg: dict) -> bool:
	    """Actualiza um registo existente identificado por fonte+nr_ordem. Devolve True se actualizou."""
	    tabela = {"batismo": "batismos", "casamento": "casamentos", "obito": "obitos"}[tipo]
	    campos_excluir = {"_folha", "_nr_linha", "fonte", "nr_ordem"}
	    campos = {k: v for k, v in reg.items() if k not in campos_excluir}
	    if not campos:
	        return False
	    set_clause = ", ".join(f"{c} = ?" for c in campos)
	    valores = list(campos.values()) + [fonte, nr_ordem]
	    conn = self._conn()
	    cur = conn.cursor()
	    cur.execute(
	        f"UPDATE {tabela} SET {set_clause} WHERE LOWER(fonte) = LOWER(?) AND LOWER(nr_ordem) = LOWER(?)",
	        valores,
	    )
	    alterado = cur.rowcount > 0
	    conn.commit()
	    conn.close()
	    return alterado
	
    def actualizar_registo_por_bio(self, tipo: str, chave: tuple, reg: dict) -> bool:
	    """Actualiza um registo existente identificado por campos biográficos. Devolve True se actualizou."""
	    tabela = {"batismo": "batismos", "casamento": "casamentos", "obito": "obitos"}[tipo]
	    campos_excluir = {"_folha", "_nr_linha"}
	    campos = {k: v for k, v in reg.items() if k not in campos_excluir}
	    conn = self._conn()
	    cur = conn.cursor()
	    if tipo == "batismo":
	        _, _, ano, nome, pai, mae = chave
	        where = "ano = ? AND LOWER(nome) = LOWER(?) AND LOWER(COALESCE(pai,'')) = LOWER(?) AND LOWER(COALESCE(mae,'')) = LOWER(?)"
	        params = list(campos.values()) + [ano, nome, pai, mae]
	    elif tipo == "casamento":
	        _, _, ano, noivo, noiva = chave
	        where = "ano = ? AND LOWER(noivo) = LOWER(?) AND LOWER(noiva) = LOWER(?)"
	        params = list(campos.values()) + [ano, noivo, noiva]
	    else:
	        _, _, ano, nome, pai, mae = chave
	        where = "ano = ? AND LOWER(nome) = LOWER(?) AND LOWER(COALESCE(pai,'')) = LOWER(?) AND LOWER(COALESCE(mae,'')) = LOWER(?)"
	        params = list(campos.values()) + [ano, nome, pai, mae]
	    set_clause = ", ".join(f"{c} = ?" for c in campos)
	    cur.execute(f"UPDATE {tabela} SET {set_clause} WHERE {where}", params)
	    alterado = cur.rowcount > 0
	    conn.commit()
	    conn.close()
	    return alterado

    def registar_acesso(self, ip: str, endpoint: str, metodo: str, 
                         status: int, user_agent: str):
        try:
            conn = self._conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO auditoria (data, ip, endpoint, metodo, status, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(timespec="seconds"),
                ip, endpoint, metodo, status, user_agent[:200] if user_agent else None
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass  # Nunca deixar auditoria quebrar o pedido principal
    
    def obter_auditoria(self) -> dict:
        conn = self._conn()
        cur = conn.cursor()
    
        # Acessos por IP nos últimos 90 dias
        cur.execute("""
            SELECT 
                ip,
                COUNT(*) as total,
                SUM(CASE WHEN endpoint LIKE '%pesquisar%' THEN 1 ELSE 0 END) as pesquisas,
                SUM(CASE WHEN endpoint LIKE '%admin%' THEN 1 ELSE 0 END) as admin,
                MIN(data) as primeiro_acesso,
                MAX(data) as ultimo_acesso
            FROM auditoria
            WHERE data >= datetime('now', '-90 days')
            GROUP BY ip
            ORDER BY total DESC
        """)
        por_ip = [dict(r) for r in cur.fetchall()]
    
        # Acessos por dia nos últimos 90 dias
        cur.execute("""
            SELECT 
                substr(data, 1, 10) as dia,
                COUNT(*) as total,
                COUNT(DISTINCT ip) as ips_unicos
            FROM auditoria
            WHERE data >= datetime('now', '-90 days')
            GROUP BY dia
            ORDER BY dia DESC
            LIMIT 90
        """)
        por_dia = [dict(r) for r in cur.fetchall()]
    
        # Endpoints mais acedidos
        cur.execute("""
            SELECT 
                endpoint,
                metodo,
                COUNT(*) as total,
                SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) as erros
            FROM auditoria
            WHERE data >= datetime('now', '-90 days')
            GROUP BY endpoint, metodo
            ORDER BY total DESC
            LIMIT 20
        """)
        por_endpoint = [dict(r) for r in cur.fetchall()]
    
        # Tentativas suspeitas (status 4xx/5xx, rate limit, admin externo)
        cur.execute("""
            SELECT data, ip, endpoint, metodo, status, user_agent
            FROM auditoria
            WHERE data >= datetime('now', '-90 days')
              AND (status = 429 OR status = 403 OR status >= 500)
            ORDER BY data DESC
            LIMIT 100
        """)
        suspeitos = [dict(r) for r in cur.fetchall()]
    
        # Totais gerais
        cur.execute("""
            SELECT 
                COUNT(*) as total_pedidos,
                COUNT(DISTINCT ip) as ips_unicos,
                SUM(CASE WHEN status >= 400 THEN 1 ELSE 0 END) as total_erros
            FROM auditoria
            WHERE data >= datetime('now', '-90 days')
        """)
        totais = dict(cur.fetchone())
    
        conn.close()
        return {
            "totais": totais,
            "por_ip": por_ip,
            "por_dia": por_dia,
            "por_endpoint": por_endpoint,
            "suspeitos": suspeitos,
        }
    
    def limpar_auditoria_antiga(self):
        """Remove registos com mais de 90 dias."""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM auditoria WHERE data < datetime('now', '-90 days')")
        conn.commit()
        conn.close()

    def listar_freguesias(self) -> List[str]:
        """Lista freguesias já introduzidas, sem duplicados."""
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT freguesia FROM uploads
            WHERE freguesia IS NOT NULL AND freguesia != ''
            ORDER BY freguesia
        """)
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        return rows
    
    def extrair_codigo_adist(self, upload_id: int, tipo: str) -> Optional[str]:
        """Extrai o código do arquivo distrital a partir dos registos importados."""
        tabela = {"batismo": "batismos", "casamento": "casamentos", "obito": "obitos"}[tipo]
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(f"""
            SELECT fonte FROM {tabela}
            WHERE upload_id = ? AND fonte IS NOT NULL
            LIMIT 1
        """, (upload_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        # Extrair código tipo PABT06 da referência PT/ADSTR/PRQ/PABT06/...
        import re
        m = re.search(r'/PRQ/([A-Z0-9]+)/', row[0])
        return m.group(1) if m else None
    
    def actualizar_codigo_adist(self, upload_id: int, codigo: str):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute("UPDATE uploads SET codigo_adist = ? WHERE id = ?", (codigo, upload_id))
        conn.commit()
        conn.close()
    
    def estatisticas_por_freguesia(self) -> List[dict]:
        """Estatísticas agrupadas por freguesia com detalhe por tipo."""
        conn = self._conn()
        cur = conn.cursor()
    
        # Obter todas as freguesias com uploads
        cur.execute("""
            SELECT DISTINCT freguesia, codigo_adist
            FROM uploads
            WHERE freguesia IS NOT NULL AND freguesia != ''
            ORDER BY freguesia
        """)
        freguesias = [{"nome": r[0], "codigo": r[1]} for r in cur.fetchall()]
    
        resultado = []
        for freg in freguesias:
            nome = freg["nome"]
            codigo = freg["codigo"]
    
            tipos = {}
            for tipo, tabela in [
                ("batismos", "batismos"),
                ("casamentos", "casamentos"),
                ("obitos", "obitos"),
            ]:
                cur.execute(f"""
                    SELECT COUNT(*) as total, MIN(ano) as ano_min, MAX(ano) as ano_max
                    FROM {tabela} t
                    JOIN uploads u ON t.upload_id = u.id
                    WHERE u.freguesia = ?
                """, (nome,))
                row = dict(cur.fetchone())
                if row["total"] > 0:
                    tipos[tipo] = row
    
            # Histórico de uploads desta freguesia
            cur.execute("""
                SELECT u.id, u.tipo, u.data_upload, u.registos, u.avisos,
                       MIN(t.ano) as ano_min, MAX(t.ano) as ano_max
                FROM uploads u
                LEFT JOIN (
                    SELECT upload_id, ano FROM batismos
                    UNION ALL
                    SELECT upload_id, ano FROM casamentos
                    UNION ALL
                    SELECT upload_id, ano FROM obitos
                ) t ON t.upload_id = u.id
                WHERE u.freguesia = ?
                GROUP BY u.id
                ORDER BY u.data_upload DESC
            """, (nome,))
            uploads = [dict(r) for r in cur.fetchall()]
    
            resultado.append({
                "nome": nome,
                "codigo_adist": codigo,
                "tipos": tipos,
                "uploads": uploads,
            })
    
        conn.close()
        return resultado
	
	# Tokens
    def _criar_tabelas_federacao(self):
        conn = self._conn()
        cur  = conn.cursor()

        # Tokens que ESTE nó emitiu para outros se ligarem a ele
        cur.execute("""
        CREATE TABLE IF NOT EXISTS tokens_emitidos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            token        TEXT NOT NULL UNIQUE,
            nome         TEXT NOT NULL,      -- ex: "Ligação com Mouriscas"
            descricao    TEXT,
            activo       INTEGER DEFAULT 1,
            data_criacao TEXT NOT NULL,
            ultimo_uso   TEXT               -- última vez que foi usado com sucesso
        )
        """)

        # Nós remotos a que ESTE nó se liga (cada um com o seu token)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS nos_federados (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            url          TEXT NOT NULL UNIQUE,
            nome         TEXT NOT NULL,
            descricao    TEXT,
            regiao       TEXT,
            token        TEXT NOT NULL,     -- token fornecido pelo owner do nó remoto
            activo       INTEGER DEFAULT 1,
            data_adicao  TEXT NOT NULL,
            ultimo_ok    TEXT,
            ultimo_erro  TEXT
        )
        """)

        conn.commit()
        conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # Tokens emitidos (este nó autoriza outros a ligarem-se)
    # ══════════════════════════════════════════════════════════════════════════

    def criar_token(self, nome: str, descricao: str = None) -> str:
        """Gera um UUID v4 e regista-o como token activo."""
        from datetime import datetime
        token = str(uuid.uuid4())
        conn  = self._conn()
        cur   = conn.cursor()
        cur.execute("""
            INSERT INTO tokens_emitidos (token, nome, descricao, data_criacao)
            VALUES (?, ?, ?, ?)
        """, (token, nome, descricao,
              datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        conn.close()
        return token

    def listar_tokens(self) -> list:
        conn = self._conn()
        cur  = conn.cursor()
        # Nunca devolver o valor do token na listagem — só os metadados
        cur.execute("""
            SELECT id, nome, descricao, activo, data_criacao, ultimo_uso,
                   substr(token,1,8) || '…' AS token_preview
            FROM tokens_emitidos
            ORDER BY data_criacao DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def validar_token(self, token: str) -> bool:
        """Verifica se o token existe e está activo; actualiza ultimo_uso."""
        from datetime import datetime
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id FROM tokens_emitidos
            WHERE token = ? AND activo = 1
        """, (token,))
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE tokens_emitidos SET ultimo_uso = ? WHERE id = ?
            """, (datetime.now().isoformat(timespec="seconds"), row[0]))
            conn.commit()
        conn.close()
        return row is not None

    def revogar_token(self, token_id: int):
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute(
            "UPDATE tokens_emitidos SET activo = 0 WHERE id = ?", (token_id,))
        conn.commit()
        conn.close()

    def remover_token(self, token_id: int):
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute("DELETE FROM tokens_emitidos WHERE id = ?", (token_id,))
        conn.commit()
        conn.close()

    # ══════════════════════════════════════════════════════════════════════════
    # Nós federados (este nó liga-se a outros)
    # ══════════════════════════════════════════════════════════════════════════

    def adicionar_no(self, url: str, nome: str, token: str,
                     descricao: str = None, regiao: str = None) -> int:
        from datetime import datetime
        url = url.rstrip("/")
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO nos_federados
                (url, nome, token, descricao, regiao, data_adicao)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url, nome, token, descricao, regiao,
              datetime.now().isoformat(timespec="seconds")))
        no_id = cur.lastrowid
        conn.commit()
        conn.close()
        return no_id

    def listar_nos(self) -> list:
        conn = self._conn()
        cur  = conn.cursor()
        # Nunca expor o token na listagem
        cur.execute("""
            SELECT id, url, nome, descricao, regiao, activo,
                   data_adicao, ultimo_ok, ultimo_erro
            FROM nos_federados
            ORDER BY nome
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def listar_nos_activos(self) -> list:
        """Inclui o token — usado internamente para fazer pedidos."""
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute("""
            SELECT id, url, nome, token
            FROM nos_federados
            WHERE activo = 1
            ORDER BY nome
        """)
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows

    def actualizar_no(self, no_id: int, campos: dict):
        permitidos = {"url", "nome", "descricao", "regiao", "activo", "token"}
        updates = {k: v for k, v in campos.items() if k in permitidos}
        if not updates:
            return
        sql = ", ".join(f"{k} = ?" for k in updates)
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute(f"UPDATE nos_federados SET {sql} WHERE id = ?",
                    (*updates.values(), no_id))
        conn.commit()
        conn.close()

    def remover_no(self, no_id: int):
        conn = self._conn()
        cur  = conn.cursor()
        cur.execute("DELETE FROM nos_federados WHERE id = ?", (no_id,))
        conn.commit()
        conn.close()

    def registar_resultado_no(self, no_id: int, sucesso: bool, erro: str = None):
        from datetime import datetime
        agora = datetime.now().isoformat(timespec="seconds")
        conn  = self._conn()
        cur   = conn.cursor()
        if sucesso:
            cur.execute("""
                UPDATE nos_federados
                SET ultimo_ok = ?, ultimo_erro = NULL
                WHERE id = ?
            """, (agora, no_id))
        else:
            cur.execute("""
                UPDATE nos_federados
                SET ultimo_erro = ?
                WHERE id = ?
            """, (f"[{agora}] {erro}", no_id))
        conn.commit()
        conn.close()
		
	# ── Verificação de duplicados ─────────────────────────────────────────────────
	
    def verificar_existencia_por_ref(self, tipo: str, pares: list) -> list:
        tabela = {"batismo": "batismos", "casamento": "casamentos", "obito": "obitos"}[tipo]
        conn = self._conn()
        cur = conn.cursor()
        resultado = []
        for fonte, nr_ordem in pares:
            cur.execute(
                f"SELECT 1 FROM {tabela} WHERE LOWER(fonte) = LOWER(?) AND LOWER(nr_ordem) = LOWER(?) LIMIT 1",
                (fonte, nr_ordem),
            )
            resultado.append(cur.fetchone() is not None)
        conn.close()
        return resultado

    def verificar_existencia_por_bio(self, tipo: str, chaves: list) -> list:
        tabela = {"batismo": "batismos", "casamento": "casamentos", "obito": "obitos"}[tipo]
        conn = self._conn()
        cur = conn.cursor()
        resultado = []
        for chave in chaves:
            if tipo == "batismo":
                _, _, ano, nome, pai, mae = chave
                cur.execute(
                    f"SELECT 1 FROM {tabela} WHERE ano = ? AND LOWER(nome) = LOWER(?) AND LOWER(COALESCE(pai, '')) = LOWER(?) AND LOWER(COALESCE(mae, '')) = LOWER(?) LIMIT 1",
                    (ano, nome, pai, mae),
                )
            elif tipo == "casamento":
                _, _, ano, noivo, noiva = chave
                cur.execute(
                    f"SELECT 1 FROM {tabela} WHERE ano = ? AND LOWER(noivo) = LOWER(?) AND LOWER(noiva) = LOWER(?) LIMIT 1",
                    (ano, noivo, noiva),
                )
            else:
                _, _, ano, nome, pai, mae = chave
                cur.execute(
                    f"SELECT 1 FROM {tabela} WHERE ano = ? AND LOWER(nome) = LOWER(?) AND LOWER(COALESCE(pai, '')) = LOWER(?) AND LOWER(COALESCE(mae, '')) = LOWER(?) LIMIT 1",
                    (ano, nome, pai, mae),
                )
            resultado.append(cur.fetchone() is not None)
        conn.close()
        return resultado
