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
import asyncio
import httpx
from pydantic import BaseModel
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

# ── Modelo para actualização de configuração ──────────────────────────────────

class ConfiguracaoPayload(BaseModel):
    valor: str
    
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
    por_pagina: int = Query(25, ge=1, le=5000),
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
    por_pagina: int = Query(25, ge=1, le=5000), #alterado aqui de 100 para 5000
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
    freguesia: str = Query(default=None, max_length=100),
    modo_actualizacao: bool = Query(False),
    _=Depends(verificar_ip_local),
):
    # verificar_rate_limit(request, "upload") -- removido rate limit para ip locais
    validar_tipo_registo(tipo)
    conteudo = await ficheiro.read()
    validar_ficheiro(ficheiro.filename, conteudo)
    importer = ExcelImporter(db)
    return importer.validar_e_importar(
        conteudo, tipo, ficheiro.filename,
        dry_run=True, freguesia=freguesia
    )

@app.post("/admin/api/confirmar-upload")
async def confirmar_upload(
    request: Request,
    ficheiro: UploadFile = File(...),
    tipo: str = Query(...),
    freguesia: str = Query(default=None, max_length=100),
    modo_actualizacao: bool = Query(False),
    _=Depends(verificar_ip_local),
):
    # verificar_rate_limit(request, "upload") -- removido rate limit para ip locais
    validar_tipo_registo(tipo)
    conteudo = await ficheiro.read()
    validar_ficheiro(ficheiro.filename, conteudo)
    importer = ExcelImporter(db)
    return importer.validar_e_importar(
        conteudo, tipo, ficheiro.filename,
        dry_run=False, freguesia=freguesia, modo_actualizacao=modo_actualizacao,
    )

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

@app.get("/api/estatisticas-freguesias")
def estatisticas_freguesias(request: Request):
    verificar_rate_limit(request, "pesquisa")
    return db.estatisticas_por_freguesia()

@app.get("/admin/api/freguesias")
def listar_freguesias(request: Request, _=Depends(verificar_ip_local)):
    return db.listar_freguesias()

@app.get("/api/configuracao/footer")
def obter_footer(request: Request):
    """Devolve o texto do footer para o frontend público."""
    verificar_rate_limit(request, "pesquisa")
    valor = db.obter_configuracao("footer_texto")
    return {"footer_texto": valor or ""}


@app.get("/admin/api/configuracao/footer")
def admin_obter_footer(request: Request, _=Depends(verificar_ip_local)):
    """Devolve o texto actual do footer para edição."""
    verificar_rate_limit(request, "admin")
    valor = db.obter_configuracao("footer_texto")
    return {"footer_texto": valor or ""}

@app.post("/admin/api/configuracao/footer")
def admin_guardar_footer(
    request: Request,
    payload: ConfiguracaoPayload,
    _=Depends(verificar_ip_local),
):
    """Actualiza o texto do footer."""
    verificar_rate_limit(request, "admin")
    texto = payload.valor.strip()
    if len(texto) > 2000:
        raise HTTPException(status_code=400, detail="Texto demasiado longo (máx. 2000 caracteres).")
    db.definir_configuracao("footer_texto", texto)
    logger.info("Footer actualizado.")
    return {"sucesso": True, "footer_texto": texto}

# ── Servir frontends estáticos ────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="frontend/public"), name="public")

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("frontend/public/index.html")

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, _=Depends(verificar_ip_local)):
    return FileResponse("frontend/admin/index.html")

app.mount("/admin/static", StaticFiles(directory="frontend/admin"), name="admin")

# Tokens
# ── Modelos ───────────────────────────────────────────────────────────────────

class TokenCreate(BaseModel):
    nome: str           # ex: "Ligação com Abrantes"
    descricao: str = None

class NoFederadoCreate(BaseModel):
    url: str
    nome: str
    token: str          # UUID v4 fornecido pelo owner do nó remoto
    descricao: str = None
    regiao: str = None

class NoFederadoUpdate(BaseModel):
    url: str = None
    nome: str = None
    descricao: str = None
    regiao: str = None
    activo: int = None  # 0 ou 1
    token: str = None


# ══════════════════════════════════════════════════════════════════════════════
# Dependência: validar token no cabeçalho Authorization
# Usada nos endpoints públicos /api/info e /api/pesquisar quando chamados
# por nós remotos. Pedidos sem token (ex: browser normal) são rejeitados.
# ══════════════════════════════════════════════════════════════════════════════

def _extrair_token(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None

def exigir_token_federacao(request: Request):
    """
    Dependência FastAPI. Valida o token Bearer nos endpoints federados.
    Lança 401 se ausente ou inválido.
    """
    token = _extrair_token(request)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Token de federação em falta.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not db.validar_token(token):
        logger.warning(f"Token de federação inválido/revogado: {token[:8]}…")
        raise HTTPException(
            status_code=401,
            detail="Token de federação inválido ou revogado.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ══════════════════════════════════════════════════════════════════════════════
# Endpoints públicos federados
# (substituem os endpoints públicos normais quando chamados por nós remotos)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/info")
def info_no(
    request: Request,
    _token=Depends(exigir_token_federacao),
):
    """
    Metadados deste nó. Exige token Bearer válido.
    Chamado pelos outros nós ao adicionar ou testar a ligação.
    """
    verificar_rate_limit(request, "pesquisa")
    stats = db.estatisticas()
    return {
        "versao":    "1.0",
        "nome":      os.environ.get("NO_NOME", "Registo Paroquial"),
        "descricao": os.environ.get("NO_DESCRICAO", ""),
        "regiao":    os.environ.get("NO_REGIAO", ""),
        "stats":     stats,
    }


@app.get("/api/pesquisar-federado-externo")
def pesquisar_externo(
    request: Request,
    q: Optional[str] = Query(None, max_length=200),
    tipo: Optional[str] = Query(None),
    ano_min: Optional[int] = None,
    ano_max: Optional[int] = None,
    fonte: Optional[str] = Query(None, max_length=100),
    pagina: int = Query(1, ge=1, le=10000),
    por_pagina: int = Query(25, ge=1, le=200),
    _token=Depends(exigir_token_federacao),
):
    """
    Endpoint de pesquisa para nós remotos. Exige token Bearer válido.
    Devolve apenas resultados locais deste nó — não encadeia federação.
    """
    verificar_rate_limit(request, "pesquisa")
    q_limpo     = sanitizar_input(q, "q")
    tipo_limpo  = validar_tipo_registo(tipo) if tipo else None
    fonte_limpa = sanitizar_input(fonte, "fonte")
    ano_min_v   = validar_ano(ano_min, "ano_min")
    ano_max_v   = validar_ano(ano_max, "ano_max")

    resultados, total = db.pesquisar(
        q=q_limpo, tipo=tipo_limpo,
        ano_min=ano_min_v, ano_max=ano_max_v,
        fonte=fonte_limpa, pagina=pagina, por_pagina=por_pagina,
    )
    return {
        "total":      total,
        "pagina":     pagina,
        "por_pagina": por_pagina,
        "paginas":    (total + por_pagina - 1) // por_pagina,
        "resultados": resultados,
    }


@app.get("/api/registo-federado/{tipo}/{id}")
def registo_externo(
    request: Request,
    tipo: str,
    id: int,
    _token=Depends(exigir_token_federacao),
):
    """Detalhe de um registo para nós remotos. Exige token Bearer válido."""
    verificar_rate_limit(request, "pesquisa")
    if tipo not in ("batismo", "casamento", "obito"):
        raise HTTPException(status_code=400, detail="Tipo inválido.")
    if not (1 <= id <= 10_000_000):
        raise HTTPException(status_code=400, detail="ID inválido.")
    registo = db.obter_registo(tipo, id)
    if not registo:
        raise HTTPException(status_code=404, detail="Registo não encontrado.")
    return registo


# ══════════════════════════════════════════════════════════════════════════════
# Pesquisa federada (agrega local + nós remotos)
# ══════════════════════════════════════════════════════════════════════════════

TIMEOUT_NO      = 5.0
MAX_POR_NO      = 200

@app.get("/api/pesquisar-federado")
async def pesquisar_federado(
    request: Request,
    q: Optional[str] = Query(None, max_length=200),
    tipo: Optional[str] = Query(None),
    ano_min: Optional[int] = None,
    ano_max: Optional[int] = None,
    fonte: Optional[str] = Query(None, max_length=100),
    pagina: int = Query(1, ge=1, le=10000),
    por_pagina: int = Query(25, ge=1, le=200),
):
    """Pesquisa pública que agrega resultados locais + nós remotos autorizados."""
    verificar_rate_limit(request, "pesquisa")
    q_limpo     = sanitizar_input(q, "q")
    tipo_limpo  = validar_tipo_registo(tipo) if tipo else None
    fonte_limpa = sanitizar_input(fonte, "fonte")
    ano_min_v   = validar_ano(ano_min, "ano_min")
    ano_max_v   = validar_ano(ano_max, "ano_max")

    nos = db.listar_nos_activos()  # inclui token

    # Pesquisa local
    resultados_locais, _ = db.pesquisar(
        q=q_limpo, tipo=tipo_limpo,
        ano_min=ano_min_v, ano_max=ano_max_v,
        fonte=fonte_limpa, pagina=1, por_pagina=MAX_POR_NO,
    )
    nome_local = os.environ.get("NO_NOME", "Este arquivo")
    url_local  = os.environ.get("NO_URL", "")
    for r in resultados_locais:
        r["_no"] = {"nome": nome_local, "url": url_local, "local": True}

    # Pesquisa remota em paralelo
    async def pesquisar_no_remoto(no: dict) -> tuple[list, str | None]:
        params = {"por_pagina": MAX_POR_NO, "pagina": 1}
        if q_limpo:     params["q"]       = q_limpo
        if tipo_limpo:  params["tipo"]    = tipo_limpo
        if ano_min_v:   params["ano_min"] = ano_min_v
        if ano_max_v:   params["ano_max"] = ano_max_v
        if fonte_limpa: params["fonte"]   = fonte_limpa

        headers = {
            "Authorization": f"Bearer {no['token']}",
            "User-Agent":    "RegistosParoquiais-Federacao/1.0",
        }
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_NO) as client:
                resp = await client.get(
                    f"{no['url']}/api/pesquisar-federado-externo",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
                resultados = data.get("resultados", [])
                for r in resultados:
                    r["_no"] = {
                        "nome":  no["nome"],
                        "url":   no["url"],
                        "local": False,
                    }
                db.registar_resultado_no(no["id"], sucesso=True)
                return resultados, None

        except httpx.TimeoutException:
            erro = "Timeout (>5 s)"
        except httpx.HTTPStatusError as e:
            erro = f"HTTP {e.response.status_code}" + (
                " — token inválido ou revogado" if e.response.status_code == 401 else ""
            )
        except Exception as e:
            erro = str(e)[:120]

        db.registar_resultado_no(no["id"], sucesso=False, erro=erro)
        return [], erro

    resultados_remotos = await asyncio.gather(
        *[pesquisar_no_remoto(no) for no in nos]
    )

    todos = list(resultados_locais)
    nos_com_erro = []
    for (res_no, erro), no in zip(resultados_remotos, nos):
        if erro:
            nos_com_erro.append({"nome": no["nome"], "erro": erro})
        else:
            todos.extend(res_no)

    todos.sort(key=lambda r: r.get("ano") or 0)
    total  = len(todos)
    inicio = (pagina - 1) * por_pagina

    return {
        "total":           total,
        "pagina":          pagina,
        "por_pagina":      por_pagina,
        "paginas":         (total + por_pagina - 1) // por_pagina,
        "resultados":      todos[inicio:inicio + por_pagina],
        "nos_consultados": len(nos) + 1,
        "nos_com_erro":    nos_com_erro,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Admin — gestão de tokens emitidos
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/api/tokens")
def listar_tokens(request: Request, _=Depends(verificar_ip_local)):
    verificar_rate_limit(request, "admin")
    return db.listar_tokens()  # nunca expõe o token completo


@app.post("/admin/api/tokens")
def criar_token(
    request: Request,
    dados: TokenCreate,
    _=Depends(verificar_ip_local),
):
    verificar_rate_limit(request, "admin")
    nome = sanitizar_input(dados.nome.strip(), "nome")
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório.")
    desc = sanitizar_input(dados.descricao, "descricao") if dados.descricao else None

    token = db.criar_token(nome=nome, descricao=desc)
    logger.info(f"Token de federação criado: '{nome}'")
    # Único momento em que o token completo é devolvido — guarda-o agora
    return {
        "token": token,
        "aviso": "Copia este token agora. Não será mostrado novamente.",
    }


@app.delete("/admin/api/tokens/{token_id}/revogar")
def revogar_token(
    request: Request,
    token_id: int,
    _=Depends(verificar_ip_local),
):
    verificar_rate_limit(request, "admin")
    db.revogar_token(token_id)
    logger.info(f"Token id={token_id} revogado.")
    return {"sucesso": True}


@app.delete("/admin/api/tokens/{token_id}")
def remover_token(
    request: Request,
    token_id: int,
    _=Depends(verificar_ip_local),
):
    verificar_rate_limit(request, "admin")
    db.remover_token(token_id)
    logger.info(f"Token id={token_id} removido.")
    return {"sucesso": True}


# ══════════════════════════════════════════════════════════════════════════════
# Admin — gestão de nós federados
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/admin/api/nos-federados")
def listar_nos(request: Request, _=Depends(verificar_ip_local)):
    verificar_rate_limit(request, "admin")
    return db.listar_nos()  # nunca expõe o token


@app.post("/admin/api/nos-federados")
async def adicionar_no(
    request: Request,
    no: NoFederadoCreate,
    _=Depends(verificar_ip_local),
):
    verificar_rate_limit(request, "admin")
    url   = sanitizar_input(no.url.strip(), "url")
    nome  = sanitizar_input(no.nome.strip(), "nome")
    token = sanitizar_input(no.token.strip(), "token")
    if not url or not nome or not token:
        raise HTTPException(
            status_code=400, detail="url, nome e token são obrigatórios.")

    # Verificar acessibilidade com o token fornecido
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{url}/api/info",
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "RegistosParoquiais-Federacao/1.0",
                },
            )
            if resp.status_code == 401:
                raise HTTPException(
                    status_code=400,
                    detail="Token rejeitado pelo nó remoto. Verifica se o token está correcto e activo."
                )
            resp.raise_for_status()
            info = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Não foi possível contactar o nó '{url}': {e}"
        )

    try:
        no_id = db.adicionar_no(
            url=url, nome=nome, token=token,
            descricao=sanitizar_input(no.descricao, "descricao") if no.descricao else None,
            regiao=sanitizar_input(no.regiao, "regiao") if no.regiao else None,
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail="Este nó já está registado.")
        raise HTTPException(status_code=500, detail=str(e))

    logger.info(f"Nó federado adicionado: {nome} ({url})")
    return {"id": no_id, "info_remota": info}


@app.patch("/admin/api/nos-federados/{no_id}")
def actualizar_no(
    request: Request,
    no_id: int,
    dados: NoFederadoUpdate,
    _=Depends(verificar_ip_local),
):
    verificar_rate_limit(request, "admin")
    campos = {k: v for k, v in dados.model_dump().items() if v is not None}
    if not campos:
        raise HTTPException(status_code=400, detail="Nenhum campo para actualizar.")
    db.actualizar_no(no_id, campos)
    return {"sucesso": True}


@app.delete("/admin/api/nos-federados/{no_id}")
def remover_no(
    request: Request,
    no_id: int,
    _=Depends(verificar_ip_local),
):
    verificar_rate_limit(request, "admin")
    db.remover_no(no_id)
    logger.info(f"Nó federado removido: id={no_id}")
    return {"sucesso": True}


@app.post("/admin/api/nos-federados/{no_id}/testar")
async def testar_no(
    request: Request,
    no_id: int,
    _=Depends(verificar_ip_local),
):
    verificar_rate_limit(request, "admin")
    nos = db.listar_nos_activos()
    no  = next((n for n in nos if n["id"] == no_id), None)
    if not no:
        raise HTTPException(status_code=404, detail="Nó não encontrado.")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{no['url']}/api/info",
                headers={
                    "Authorization": f"Bearer {no['token']}",
                    "User-Agent": "RegistosParoquiais-Federacao/1.0",
                },
            )
            if resp.status_code == 401:
                db.registar_resultado_no(no_id, sucesso=False, erro="Token rejeitado (401)")
                return {"sucesso": False, "erro": "Token rejeitado pelo nó remoto."}
            resp.raise_for_status()
            info = resp.json()
        db.registar_resultado_no(no_id, sucesso=True)
        return {"sucesso": True, "info": info}
    except Exception as e:
        erro = str(e)[:120]
        db.registar_resultado_no(no_id, sucesso=False, erro=erro)
        return {"sucesso": False, "erro": erro}

# evita expor o token ao browser
@app.get("/api/registo-proxy")
async def registo_proxy(
    request: Request,
    url: str = Query(..., max_length=200),
    tipo: str = Query(...),
    id: int = Query(...),
):
    """Proxy autenticado para detalhe de registo remoto."""
    verificar_rate_limit(request, "pesquisa")
    if tipo not in ("batismo", "casamento", "obito"):
        raise HTTPException(status_code=400, detail="Tipo inválido.")

    # Encontrar o nó correspondente e o seu token
    nos = db.listar_nos_activos()
    no  = next((n for n in nos if url.startswith(n["url"])), None)
    if not no:
        raise HTTPException(status_code=403, detail="Nó não autorizado.")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{no['url']}/api/registo-federado/{tipo}/{id}",
                headers={
                    "Authorization": f"Bearer {no['token']}",
                    "User-Agent": "RegistosParoquiais-Federacao/1.0",
                },
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:120])

if __name__ == "__main__":
    db.criar_tabelas()
    uvicorn.run("main:app", host="0.0.0.0", port=9000, reload=False)
