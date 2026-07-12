from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional
import uvicorn
import os
import anthropic
import json
import re
import logging

from database import Database
from importer import ExcelImporter
from security import (
    verificar_rate_limit, sanitizar_input, validar_tipo_registo,
    validar_ano, validar_pagina, validar_ficheiro, SECURITY_HEADERS, logger, AuditoriaMiddleware
)

app = FastAPI(title="Registos Paroquiais API", docs_url=None, redoc_url=None)

# ── Middleware: headers de segurança ──────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        for header, valor in SECURITY_HEADERS.items():
            response.headers[header] = valor
        # Registar acesso
        await auditoria_mw.registar(request, response.status_code)
        return response

app.add_middleware(SecurityHeadersMiddleware)

# CORS restrito — apenas GET e métodos necessários
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
    max_age=600,
)

db = Database()
auditoria_mw = AuditoriaMiddleware(db)

# ── Protecção de IP local para admin ─────────────────────────────────────────

LOCAL_NETWORKS = ("127.", "192.168.", "10.", "172.")

def verificar_ip_local(request: Request):
    forwarded = request.headers.get("X-Forwarded-For")
    client_ip = forwarded.split(",")[0].strip() if forwarded else request.client.host
    if not any(client_ip.startswith(p) for p in LOCAL_NETWORKS):
        logger.warning(f"Tentativa de acesso admin de IP externo: {client_ip}")
        raise HTTPException(status_code=403, detail="Acesso restrito à rede local.")
    return client_ip

# ── Rotas públicas ────────────────────────────────────────────────────────────

@app.get("/api/pesquisar")
def pesquisar(
    request: Request,
    q: Optional[str] = Query(None, max_length=200),
    tipo: Optional[str] = Query(None),
    ano_min: Optional[int] = None,
    ano_max: Optional[int] = None,
    fonte: Optional[str] = Query(None, max_length=100),
    pagina: int = Query(1, ge=1, le=10000),
    por_pagina: int = Query(25, ge=1, le=100),
):
    verificar_rate_limit(request, "pesquisa")
    q_limpo     = sanitizar_input(q, "q")
    tipo_limpo  = validar_tipo_registo(tipo) if tipo else None
    fonte_limpa = sanitizar_input(fonte, "fonte")
    ano_min     = validar_ano(ano_min, "ano_min")
    ano_max     = validar_ano(ano_max, "ano_max")

    resultados, total = db.pesquisar(
        q=q_limpo, tipo=tipo_limpo, ano_min=ano_min, ano_max=ano_max,
        fonte=fonte_limpa, pagina=pagina, por_pagina=por_pagina
    )
    return {
        "total": total, "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": (total + por_pagina - 1) // por_pagina,
        "resultados": resultados,
    }

@app.get("/api/registo/{tipo}/{id}")
def detalhe_registo(request: Request, tipo: str, id: int):
    verificar_rate_limit(request, "pesquisa")
    if tipo not in ("batismo", "casamento", "obito"):
        raise HTTPException(status_code=400, detail="Tipo inválido.")
    if not (1 <= id <= 10_000_000):
        raise HTTPException(status_code=400, detail="ID inválido.")
    registo = db.obter_registo(tipo, id)
    if not registo:
        raise HTTPException(status_code=404, detail="Registo não encontrado.")
    return registo

@app.get("/api/estatisticas")
def estatisticas(request: Request):
    verificar_rate_limit(request, "pesquisa")
    return db.estatisticas()

@app.get("/api/estatisticas-detalhadas")
def estatisticas_detalhadas(request: Request):
    verificar_rate_limit(request, "pesquisa")
    return db.estatisticas_detalhadas()

@app.get("/api/fontes")
def listar_fontes(request: Request):
    verificar_rate_limit(request, "pesquisa")
    return db.listar_fontes()

@app.get("/api/pesquisar-ia")
async def pesquisar_ia(
    request: Request,
    q: str = Query(..., max_length=300),
    pagina: int = Query(1, ge=1, le=10000),
    por_pagina: int = Query(25, ge=1, le=100),
    _=Depends(verificar_ip_local),
):
    verificar_rate_limit(request, "ia")
    q_limpo = sanitizar_input(q, "q")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="API de IA não configurada.")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resposta = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=300,
            system="""Responde APENAS com um objecto JSON válido, sem texto adicional, sem markdown, sem explicações.
Interpreta a pesquisa genealógica e extrai os campos relevantes:
- nome, pai, mae, noivo, noiva, testemunha, local, fonte, ano_min, ano_max, tipo
- avo_paterno, avo_paterna, avo_materno, avo_materna (avós paternos e maternos)

Exemplos:
Input: "joão filho de pedro"
Output: {"nome":"joão","pai":"pedro"}

Input: "filho de joão frade e maria salgueira"
Output: {"pai":"joão frade","mae":"maria salgueira"}

Input: "neto paterno de manuel silva"
Output: {"avo_paterno":"manuel silva"}

Input: "cuja avó materna era isabel sousa"
Output: {"avo_materna":"isabel sousa"}

Input: "casamentos da família silva em 1823"
Output: {"tipo":"casamento","nome":"silva","ano_min":1823,"ano_max":1823}

Devolve APENAS o JSON. Nenhuma palavra adicional.""",
            messages=[{"role": "user", "content": q_limpo}]
        )

        filtros_raw = resposta.content[0].text.strip()
        if filtros_raw.startswith("```"):
            filtros_raw = filtros_raw.split("```")[1]
            if filtros_raw.startswith("json"):
                filtros_raw = filtros_raw[4:]
            filtros_raw = filtros_raw.strip()
        match = re.search(r'\{.*\}', filtros_raw, re.DOTALL)
        filtros_raw = match.group(0) if match else filtros_raw
        filtros = json.loads(filtros_raw)
        usou_ia = True

    except Exception:
        from parser import interpretar_query
        filtros = interpretar_query(q_limpo)
        usou_ia = False

    termos = [filtros.get(c) for c in (
        "nome", "pai", "mae", "noivo", "noiva", "testemunha",
        "avo_paterno", "avo_paterna", "avo_materno", "avo_materna"
    ) if filtros.get(c)]
    q_combinado = " ".join(termos) if termos else None

    resultados, total = db.pesquisar(
        q=q_combinado, tipo=filtros.get("tipo"),
        ano_min=filtros.get("ano_min"), ano_max=filtros.get("ano_max"),
        fonte=filtros.get("fonte"), pagina=pagina, por_pagina=por_pagina,
    )
    return {
        "total": total, "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": (total + por_pagina - 1) // por_pagina,
        "resultados": resultados,
        "interpretacao": filtros,
        "usou_ia": usou_ia,
    }

# ── Rotas de administração ────────────────────────────────────────────────────

@app.get("/admin/api/uploads")
def listar_uploads(request: Request, _=Depends(verificar_ip_local)):
    verificar_rate_limit(request, "admin")
    return db.listar_uploads()

@app.get("/admin/api/auditoria")
def obter_auditoria(request: Request, _=Depends(verificar_ip_local)):
    verificar_rate_limit(request, "admin")
    db.limpar_auditoria_antiga()
    return db.obter_auditoria()

@app.post("/admin/api/upload")
async def fazer_upload(
    request: Request,
    ficheiro: UploadFile = File(...),
    tipo: str = Query(...),
    _=Depends(verificar_ip_local),
):
    verificar_rate_limit(request, "upload")
    validar_tipo_registo(tipo)
    conteudo = await ficheiro.read()
    validar_ficheiro(ficheiro.filename, conteudo)
    importer = ExcelImporter(db)
    return importer.validar_e_importar(conteudo, tipo, ficheiro.filename, dry_run=True)

@app.post("/admin/api/confirmar-upload")
async def confirmar_upload(
    request: Request,
    ficheiro: UploadFile = File(...),
    tipo: str = Query(...),
    _=Depends(verificar_ip_local),
):
    verificar_rate_limit(request, "upload")
    validar_tipo_registo(tipo)
    conteudo = await ficheiro.read()
    validar_ficheiro(ficheiro.filename, conteudo)
    importer = ExcelImporter(db)
    return importer.validar_e_importar(conteudo, tipo, ficheiro.filename, dry_run=False)

@app.delete("/admin/api/reset-db")
def reset_db(request: Request, confirmar: str = Query(...), _=Depends(verificar_ip_local)):
    verificar_rate_limit(request, "admin")
    if confirmar != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Passa o parâmetro confirmar=CONFIRMAR.")
    conn = db._conn()
    cur = conn.cursor()
    for tabela in ("batismos", "casamentos", "obitos", "uploads"):
        cur.execute(f"DELETE FROM {tabela}")
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('batismos','casamentos','obitos','uploads')")
    conn.commit()
    conn.close()
    logger.info("Base de dados reinicializada.")
    return {"sucesso": True, "mensagem": "Base de dados limpa."}

# ── Servir frontends estáticos ────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="frontend/public"), name="public")

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("frontend/public/index.html")

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, _=Depends(verificar_ip_local)):
    return FileResponse("frontend/admin/index.html")

app.mount("/admin/static", StaticFiles(directory="frontend/admin"), name="admin")

if __name__ == "__main__":
    db.criar_tabelas()
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
