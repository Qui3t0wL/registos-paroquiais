import re
from typing import Optional

SECULO_PARA_ANOS = {
    "XVI": (1500, 1599), "XVII": (1600, 1699), "XVIII": (1700, 1799),
    "XIX": (1800, 1899), "XX": (1900, 1999), "XXI": (2000, 2099),
}

def interpretar_query(q: str) -> dict:
    """Interpreta uma query genealógica em português usando padrões regex."""
    filtros = {}
    texto = q.strip()

    # Tipo de registo
    if re.search(r'\b(batismo|batismos|baptismo|baptismos|nasc\w*)\b', texto, re.I):
        filtros["tipo"] = "batismo"
    elif re.search(r'\b(casamento|casamentos|casou|casada|casado|noivo|noiva)\b', texto, re.I):
        filtros["tipo"] = "casamento"
    elif re.search(r'\b(óbito|obito|óbitos|obitos|morte|morreu|falec\w*)\b', texto, re.I):
        filtros["tipo"] = "obito"

    # Século
    for romano, (ano_min, ano_max) in SECULO_PARA_ANOS.items():
        if re.search(rf'\bséculo\s+{romano}\b', texto, re.I):
            filtros["ano_min"] = ano_min
            filtros["ano_max"] = ano_max
            break

    # Ano exacto ou aproximado
    if "ano_min" not in filtros:
        m = re.search(r'\b(por volta de|circa|c\.?|~)?\s*(1[4-9]\d{2}|20[0-2]\d)\b', texto, re.I)
        if m:
            ano = int(m.group(2))
            aproximado = bool(m.group(1))
            filtros["ano_min"] = ano - 5 if aproximado else ano
            filtros["ano_max"] = ano + 5 if aproximado else ano

    # Intervalo de anos
    m = re.search(r'\b(1[4-9]\d{2}|20[0-2]\d)\s*[-–a]\s*(1[4-9]\d{2}|20[0-2]\d)\b', texto)
    if m:
        filtros["ano_min"] = int(m.group(1))
        filtros["ano_max"] = int(m.group(2))

    # "filho/a de X" ou "filha de X"
    m = re.search(r'\bfilh[oa]\s+de\s+([A-Za-zÀ-ú\s]+?)(?:\s+e\s+|\s+casad|\s+em\b|$)', texto, re.I)
    if m:
        filtros["pai"] = m.group(1).strip().title()

    # "filho de X e Y" (pai e mãe)
    m = re.search(r'\bfilh[oa]\s+de\s+([A-Za-zÀ-ú]+(?:\s+[A-Za-zÀ-ú]+)*)\s+e\s+([A-Za-zÀ-ú]+(?:\s+[A-Za-zÀ-ú]+)*)', texto, re.I)
    if m:
        filtros["pai"] = m.group(1).strip().title()
        filtros["mae"] = m.group(2).strip().title()

    # "casado com" / "casada com"
    m = re.search(r'\bcasad[oa]\s+com\s+([A-Za-zÀ-ú\s]+?)(?:\s+em\b|$)', texto, re.I)
    if m:
        filtros["noiva"] = m.group(1).strip().title()

    # "X e Y" como casal (apenas em contexto de casamento)
    if filtros.get("tipo") == "casamento":
        m = re.search(r'^([A-Za-zÀ-ú\s]+?)\s+e\s+([A-Za-zÀ-ú\s]+?)(?:\s+em\b|$)', texto, re.I)
        if m:
            filtros["noivo"] = m.group(1).strip().title()
            filtros["noiva"] = m.group(2).strip().title()

    # "família X" → pesquisa por apelido
    m = re.search(r'\bfamília\s+([A-Za-zÀ-ú]+)', texto, re.I)
    if m:
        filtros["nome"] = m.group(1).strip().title()

    # "em <local>" — só se não for ano
    m = re.search(r'\bem\s+([A-Za-zÀ-ú][A-Za-zÀ-ú\s]{2,})(?:\s+em\b|\s+n[oa]\b|$)', texto, re.I)
    if m:
        candidato = m.group(1).strip()
        if not re.match(r'^\d+$', candidato):
            filtros["local"] = candidato.title()

    # Avós com ramo explícito
    m = re.search(r'\bav[oô]\s+paterno\s+(?:era\s+)?([A-Za-zÀ-ú\s]+?)(?:\s+e\s+|\s+em\b|$)', texto, re.I)
    if m:
        filtros["avo_paterno"] = m.group(1).strip().title()
    
    m = re.search(r'\bav[oó]\s+paterna\s+(?:era\s+)?([A-Za-zÀ-ú\s]+?)(?:\s+e\s+|\s+em\b|$)', texto, re.I)
    if m:
        filtros["avo_paterna"] = m.group(1).strip().title()
    
    m = re.search(r'\bav[oô]\s+materno\s+(?:era\s+)?([A-Za-zÀ-ú\s]+?)(?:\s+e\s+|\s+em\b|$)', texto, re.I)
    if m:
        filtros["avo_materno"] = m.group(1).strip().title()
    
    m = re.search(r'\bav[oó]\s+materna\s+(?:era\s+)?([A-Za-zÀ-ú\s]+?)(?:\s+e\s+|\s+em\b|$)', texto, re.I)
    if m:
        filtros["avo_materna"] = m.group(1).strip().title()
    
    # "neto/a paterno/a de X"
    m = re.search(r'\bneto[a]?\s+paterno[a]?\s+de\s+([A-Za-zÀ-ú\s]+?)(?:\s+e\s+|\s+em\b|$)', texto, re.I)
    if m:
        filtros["avo_paterno"] = m.group(1).strip().title()
    
    m = re.search(r'\bneto[a]?\s+materno[a]?\s+de\s+([A-Za-zÀ-ú\s]+?)(?:\s+e\s+|\s+em\b|$)', texto, re.I)
    if m:
        filtros["avo_materno"] = m.group(1).strip().title()
    
    # Nome principal — primeira(s) palavra(s) que não foram consumidas por outros padrões
    # Remove padrões já interpretados para isolar o nome
    resto = texto
    for pattern in [
        r'\bfilh[oa]\s+de\s+.+', r'\bcasad[oa]\s+com\s+.+',
        r'\bfamília\s+\w+', r'\bséculo\s+[IVXLC]+',
        r'\bpor volta de\s+\d+', r'\b\d{4}\b',
        r'\bem\s+[A-Za-zÀ-ú\s]+',
        r'\b(batismo|casamento|óbito|obito|nasc\w*|morte|falec\w*)\b',
    ]:
        resto = re.sub(pattern, '', resto, flags=re.I).strip()

    resto = re.sub(r'\s+', ' ', resto).strip()
    if resto and len(resto) > 2 and "nome" not in filtros:
        filtros["nome"] = resto.title()

    return filtros
