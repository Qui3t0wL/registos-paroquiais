from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from typing import Optional
import uvicorn
import os
import anthropic
import json

from database import Database
from importer import ExcelImporter

app = FastAPI(title="Registos Paroquiais API")

# CORS para o frontend público
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

db = Database()

# ── Middleware: proteger /admin por IP local ──────────────────────────────────
LOCAL_NETWORKS = ("127.", "192.168.", "10.", "172.")

def verificar_ip_local(request: Request):
    client_ip = request.client.host
    # Suporte a proxy reverso (nginx, etc.)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    if not any(client_ip.startswith(prefix) for prefix in LOCAL_NETWORKS):
        raise HTTPException(status_code=403, detail="Acesso restrito à rede local.")
    return client_ip

# ── Rotas públicas: pesquisa ──────────────────────────────────────────────────

@app.get("/api/pesquisar")
def pesquisar(
    q: Optional[str] = Query(None, description="Termo de pesquisa (nome, notas...)"),
    tipo: Optional[str] = Query(None, description="batismo | casamento | obito"),
    ano_min: Optional[int] = None,
    ano_max: Optional[int] = None,
    fonte: Optional[str] = None,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=100),
):
    resultados, total = db.pesquisar(
        q=q, tipo=tipo, ano_min=ano_min, ano_max=ano_max,
        fonte=fonte, pagina=pagina, por_pagina=por_pagina
    )
    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": (total + por_pagina - 1) // por_pagina,
        "resultados": resultados,
    }

@app.get("/api/registo/{tipo}/{id}")
def detalhe_registo(tipo: str, id: int):
    if tipo not in ("batismo", "casamento", "obito"):
        raise HTTPException(status_code=400, detail="Tipo inválido.")
    registo = db.obter_registo(tipo, id)
    if not registo:
        raise HTTPException(status_code=404, detail="Registo não encontrado.")
    return registo

@app.get("/api/estatisticas")
def estatisticas():
    return db.estatisticas()

@app.get("/api/fontes")
def listar_fontes():
    return db.listar_fontes()

# ── Rotas de administração (apenas rede local) ────────────────────────────────

@app.get("/admin/api/uploads")
def listar_uploads(request: Request, _=Depends(verificar_ip_local)):
    return db.listar_uploads()

@app.post("/admin/api/upload")
async def fazer_upload(
    request: Request,
    ficheiro: UploadFile = File(...),
    tipo: str = Query(..., description="batismo | casamento | obito"),
    _=Depends(verificar_ip_local),
):
    if tipo not in ("batismo", "casamento", "obito"):
        raise HTTPException(status_code=400, detail="Tipo inválido.")
    if not ficheiro.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Apenas ficheiros Excel (.xlsx, .xls).")

    conteudo = await ficheiro.read()
    importer = ExcelImporter(db)
    resultado = importer.validar_e_importar(conteudo, tipo, ficheiro.filename, dry_run=True)
    return resultado

@app.post("/admin/api/confirmar-upload")
async def confirmar_upload(
    request: Request,
    ficheiro: UploadFile = File(...),
    tipo: str = Query(..., description="batismo | casamento | obito"),
    _=Depends(verificar_ip_local),
):
    if tipo not in ("batismo", "casamento", "obito"):
        raise HTTPException(status_code=400, detail="Tipo inválido.")

    conteudo = await ficheiro.read()
    importer = ExcelImporter(db)
    resultado = importer.validar_e_importar(conteudo, tipo, ficheiro.filename, dry_run=False)
    return resultado

@app.delete("/admin/api/reset-db")
def reset_db(request: Request, confirmar: str = Query(...), _=Depends(verificar_ip_local)):
    if confirmar != "CONFIRMAR":
        raise HTTPException(status_code=400, detail="Passa o parâmetro confirmar=CONFIRMAR para prosseguir.")
    
    conn = db._conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM batismos")
    cur.execute("DELETE FROM casamentos")
    cur.execute("DELETE FROM obitos")
    cur.execute("DELETE FROM uploads")
    cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('batismos','casamentos','obitos','uploads')")
    conn.commit()
    conn.close()
    
    return {"sucesso": True, "mensagem": "Base de dados limpa. Todos os registos e histórico de uploads foram apagados."}

@app.get("/api/pesquisar-ia")
async def pesquisar_ia(
    q: str = Query(..., description="Pesquisa em linguagem natural"),
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(25, ge=1, le=100),
):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="API de IA não configurada.")

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resposta = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system="""Interpreta pesquisas genealógicas em português e devolve APENAS JSON válido,
sem texto adicional, com os seguintes campos opcionais:
- nome: nome da pessoa principal
- pai: nome do pai
- mae: nome da mãe
- noivo: nome do noivo (casamentos)
- noiva: nome da noiva (casamentos)
- testemunha: nome de testemunha
- local: localidade
- fonte: referência de arquivo
- ano_min: ano mínimo (inteiro)
- ano_max: ano máximo (inteiro)
- tipo: "batismo", "casamento" ou "obito"

Exemplos:
"joão filho de pedro" → {"nome":"joão","pai":"pedro"}
"casamentos da família silva em 1823" → {"tipo":"casamento","nome":"silva","ano_min":1823,"ano_max":1823}
"óbitos no século XIX em aldeia do meio" → {"tipo":"obito","ano_min":1800,"ano_max":1899,"local":"aldeia do meio"}
"manuel casado com ana ferreira" → {"tipo":"casamento","noivo":"manuel","noiva":"ana ferreira"}

Omite campos não mencionados. Devolve apenas o JSON.""",
            messages=[{"role": "user", "content": q}]
        )

        filtros = json.loads(resposta.content[0].text)
        usou_ia = True

    except Exception as e:
        import traceback
        traceback.print_exc()  # aparece nos logs do docker
        # Fallback para interpretação por padrões
        from parser import interpretar_query
        filtros = interpretar_query(q)
        usou_ia = False

    # Construir termo de pesquisa combinando campos de nome
    termos = [filtros.get(c) for c in ("nome","pai","mae","noivo","noiva","testemunha") if filtros.get(c)]
    q_combinado = " ".join(termos) if termos else None

    resultados, total = db.pesquisar(
        q=q_combinado,
        tipo=filtros.get("tipo"),
        ano_min=filtros.get("ano_min"),
        ano_max=filtros.get("ano_max"),
        fonte=filtros.get("fonte"),
        pagina=pagina,
        por_pagina=por_pagina,
    )

    return {
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "paginas": (total + por_pagina - 1) // por_pagina,
        "resultados": resultados,
        "interpretacao": filtros,  # mostra ao utilizador o que foi interpretado
        "usou_ia": usou_ia,
    }

@app.get("/api/estatisticas-detalhadas")
def estatisticas_detalhadas():
    return db.estatisticas_detalhadas()
    
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
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
