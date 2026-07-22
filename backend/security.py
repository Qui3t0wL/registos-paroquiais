import re
import time
import logging
from typing import Optional
from fastapi import Request, HTTPException
from collections import defaultdict

# ── Logging de segurança ──────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger("seguranca")

# ── Rate limiting simples em memória ─────────────────────────────────────────

class RateLimiter:
    def __init__(self):
        self.pedidos: dict = defaultdict(list)
        self.bloqueados: dict = {}

    def _limpar_antigos(self, ip: str, janela: int):
        agora = time.time()
        self.pedidos[ip] = [t for t in self.pedidos[ip] if agora - t < janela]

    def verificar(self, ip: str, limite: int, janela: int, endpoint: str) -> bool:
        agora = time.time()

        # Verificar se está bloqueado
        if ip in self.bloqueados:
            if agora < self.bloqueados[ip]:
                logger.warning(f"IP bloqueado tentou aceder: {ip} → {endpoint}")
                return False
            else:
                del self.bloqueados[ip]

        self._limpar_antigos(ip, janela)
        self.pedidos[ip].append(agora)

        if len(self.pedidos[ip]) > limite:
            # Bloquear por 5 minutos após exceder o limite
            self.bloqueados[ip] = agora + 300
            logger.warning(f"Rate limit excedido — IP bloqueado 5min: {ip} → {endpoint}")
            return False

        return True

rate_limiter = RateLimiter()

# ── Limites por tipo de endpoint ──────────────────────────────────────────────

LIMITES = {
    "pesquisa":   {"limite": 60,  "janela": 60},   # 60 pedidos/minuto
    "ia":         {"limite": 10,  "janela": 60},   # 10 pedidos/minuto
    "upload":     {"limite": 10,  "janela": 300},  # 10 uploads/5 minutos
    "admin":      {"limite": 30,  "janela": 60},   # 30 pedidos/minuto
}

def verificar_rate_limit(request: Request, tipo: str):
    ip = _obter_ip(request)
    cfg = LIMITES.get(tipo, {"limite": 30, "janela": 60})
    if not rate_limiter.verificar(ip, cfg["limite"], cfg["janela"], request.url.path):
        raise HTTPException(
            status_code=429,
            detail="Demasiados pedidos. Tente novamente mais tarde."
        )

# ── Obter IP real ─────────────────────────────────────────────────────────────

def _obter_ip(request: Request) -> str:
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host

# ── Validação de inputs ───────────────────────────────────────────────────────

# Padrões suspeitos comuns em ataques
PADROES_MALICIOSOS = [
    r"(\bUNION\b.*\bSELECT\b)",           # SQL injection
    r"(\bDROP\b.*\bTABLE\b)",             # SQL injection
    r"(\bINSERT\b.*\bINTO\b)",            # SQL injection
    r"(\bDELETE\b.*\bFROM\b)",            # SQL injection
    r"(\bEXEC\b|\bEXECUTE\b)",            # SQL injection
    r"(<script[\s>])",                     # XSS
    r"(javascript\s*:)",                   # XSS
    r"(on\w+\s*=\s*[\"'])",              # XSS event handlers
    r"(\.\./|\.\.\\)",                    # Path traversal
    r"(/etc/passwd|/etc/shadow)",          # LFI
    r"(\$\{.*\}|\$\(.*\))",              # Template injection
]

REGEX_MALICIOSOS = [re.compile(p, re.IGNORECASE) for p in PADROES_MALICIOSOS]

def sanitizar_input(valor: Optional[str], campo: str = "input") -> Optional[str]:
    if valor is None:
        return None

    # Limite de tamanho
    if len(valor) > 500:
        logger.warning(f"Input demasiado longo no campo '{campo}': {len(valor)} chars")
        raise HTTPException(status_code=400, detail=f"Campo '{campo}' demasiado longo.")

    # Verificar padrões maliciosos
    for regex in REGEX_MALICIOSOS:
        if regex.search(valor):
            logger.warning(f"Padrão malicioso detectado no campo '{campo}': {valor[:100]}")
            raise HTTPException(status_code=400, detail="Input inválido.")

    return valor.strip()

def validar_tipo_registo(tipo: str) -> str:
    if tipo not in ("batismo", "casamento", "obito"):
        raise HTTPException(status_code=400, detail="Tipo de registo inválido.")
    return tipo

def validar_ano(ano: Optional[int], campo: str) -> Optional[int]:
    if ano is None:
        return None
    if not (1400 <= ano <= 2100):
        raise HTTPException(status_code=400, detail=f"Ano inválido no campo '{campo}'.")
    return ano

def validar_pagina(pagina: int) -> int:
    if not (1 <= pagina <= 10000):
        raise HTTPException(status_code=400, detail="Número de página inválido.")
    return pagina

# ── Validação de ficheiros ────────────────────────────────────────────────────

TAMANHO_MAX_UPLOAD = 50 * 1024 * 1024  # 50 MB
EXTENSOES_PERMITIDAS = (".xlsx", ".xls")
MAGIC_BYTES_XLSX = b"PK\x03\x04"  # ZIP (xlsx é um zip)
MAGIC_BYTES_XLS  = b"\xd0\xcf\x11\xe0"  # OLE2

def validar_ficheiro(nome: str, conteudo: bytes):
    # Extensão
    if not any(nome.lower().endswith(ext) for ext in EXTENSOES_PERMITIDAS):
        raise HTTPException(status_code=400, detail="Apenas ficheiros .xlsx ou .xls.")

    # Tamanho
    if len(conteudo) > TAMANHO_MAX_UPLOAD:
        raise HTTPException(status_code=400, detail="Ficheiro demasiado grande (máx. 50 MB).")

    # Verificar magic bytes (conteúdo real)
    if nome.lower().endswith(".xlsx") and not conteudo.startswith(MAGIC_BYTES_XLSX):
        logger.warning(f"Ficheiro .xlsx com conteúdo inválido: {nome}")
        raise HTTPException(status_code=400, detail="Ficheiro .xlsx inválido.")
    if nome.lower().endswith(".xls") and not conteudo.startswith(MAGIC_BYTES_XLS):
        logger.warning(f"Ficheiro .xls com conteúdo inválido: {nome}")
        raise HTTPException(status_code=400, detail="Ficheiro .xls inválido.")

# ── Headers de segurança ──────────────────────────────────────────────────────

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self';"
    ),
}
# ── Middleware de auditoria ───────────────────────────────────────────────────

class AuditoriaMiddleware:
    """Regista todos os acessos na base de dados."""
    
    # Endpoints a não registar (demasiado ruidosos)
    EXCLUIR = ("/static", "/admin/static", "/favicon")

    def __init__(self, db):
        self.db = db

    def deve_registar(self, path: str) -> bool:
        return not any(path.startswith(e) for e in self.EXCLUIR)

    async def registar(self, request: Request, status: int):
        if not self.deve_registar(request.url.path):
            return
        ip = _obter_ip(request)
        user_agent = request.headers.get("User-Agent", "")
        self.db.registar_acesso(
            ip=ip,
            endpoint=request.url.path,
            metodo=request.method,
            status=status,
            user_agent=user_agent,
        )
