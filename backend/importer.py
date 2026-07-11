import io
import re
from typing import Any, Optional
import openpyxl
from database import Database

# Mapeamento de colunas do Excel para campos internos
COLUNAS_BATISMO = {
    "FONTE (Código de refª)": "fonte",
    "FLS": "fls",
    "ANO": "ano",
    "Nº ORDEM": "nr_ordem",
    "NOME": "nome",
    "DATA NASC": "data_nasc",
    "LOCAL NASCIMENTO": "local_nascimento",
    "PAI": "pai",
    "MÃE": "mae",
    "AVÔ PATERNO": "avo_paterno",
    "AVÓ PATERNA": "avo_paterna",
    "AVÔ MATERNO": "avo_materno",
    "AVÓ MATERNA": "avo_materna",
    "NOTAS": "notas",
}

COLUNAS_CASAMENTO = {
    "FONTE (Código de refª)": "fonte",
    "FLS": "fls",
    "ANO": "ano",
    "Nº ORDEM": "nr_ordem",
    "DATA": "data",
    "NOIVO": "noivo",
    "IDADE/DNASC NOIVO": "idade_dnasc_noivo",
    "NAT. NOIVO": "nat_noivo",
    "NOIVA": "noiva",
    "IDADE/DNASC NOIVA": "idade_dnasc_noiva",
    "NAT. NOIVA": "nat_noiva",
    "LOCAL": "local",
    "PAI NOIVO": "pai_noivo",
    "NAT PAI Nº": "nat_pai_noivo",
    "MÃE NOIVO": "mae_noivo",
    "NAT MÃE Nº": "nat_mae_noivo",
    "PAI NOIVA": "pai_noiva",
    "NAT PAI Nª": "nat_pai_noiva",
    "MÃE NOIVA": "mae_noiva",
    "NAT MÃE Nª": "nat_mae_noiva",
    "TESTEMUNHA 1": "testemunha1",
    "TESTEMUNHA 2": "testemunha2",
    "NOTAS": "notas",
}

COLUNAS_OBITO = {
    "FONTE (Código de refª)": "fonte",
    "FLS": "fls",
    "ANO": "ano",
    "Nº ORDEM": "nr_ordem",
    "NOME": "nome",
    "DATA ÓBITO": "data_obito",
    "LOCAL": "local",
    "PAI": "pai",
    "MÃE": "mae",
    "NOTAS": "notas",
}

MAPA_COLUNAS = {
    "batismo": COLUNAS_BATISMO,
    "casamento": COLUNAS_CASAMENTO,
    "obito": COLUNAS_OBITO,
}

CAMPOS_OBRIGATORIOS = {
    "batismo": ["nome", "ano"],
    "casamento": ["noivo", "noiva", "ano"],
    "obito": ["nome", "ano"],
}

ANO_MIN = 1500
ANO_MAX = 2100


def limpar(val: Any) -> str:
    if val is None:
        return "n/d"
    s = str(val).strip()
    return s if s else "n/d"


def validar_ano(val: Any) -> tuple[Optional[int], Optional[str]]:
    """Devolve (ano_int, aviso) onde aviso é None se OK."""
    if val is None:
        return None, "Ano em falta"
    try:
        ano = int(float(str(val)))
    except (ValueError, TypeError):
        return None, f"Ano inválido: '{val}'"
    if not (ANO_MIN <= ano <= ANO_MAX):
        return ano, f"Ano fora do intervalo esperado ({ANO_MIN}-{ANO_MAX}): {ano}"
    return ano, None


class ExcelImporter:
    def __init__(self, db: Database):
        self.db = db

    def validar_e_importar(
        self, conteudo: bytes, tipo: str, nome_ficheiro: str, dry_run: bool
    ) -> dict:
        mapa = MAPA_COLUNAS[tipo]
        obrigatorios = CAMPOS_OBRIGATORIOS[tipo]

        try:
            wb = openpyxl.load_workbook(
                io.BytesIO(conteudo), read_only=True, data_only=True
            )
        except Exception as e:
            return {"sucesso": False, "erro": f"Não foi possível abrir o ficheiro: {e}"}

        todos_registos = []
        todos_avisos = []
        erros_criticos = []

        for nome_folha in wb.sheetnames:
            ws = wb[nome_folha]
            registos_folha, avisos_folha, erros_folha = self._processar_folha(
                ws, nome_folha, tipo, mapa, obrigatorios
            )
            todos_registos.extend(registos_folha)
            todos_avisos.extend(avisos_folha)
            erros_criticos.extend(erros_folha)

        wb.close()

        resumo = {
            "sucesso": True,
            "ficheiro": nome_ficheiro,
            "tipo": tipo,
            "total_registos": len(todos_registos),
            "total_avisos": len(todos_avisos),
            "total_erros": len(erros_criticos),
            "avisos": todos_avisos[:100],  # limitar para não sobrecarregar a resposta
            "erros": erros_criticos[:50],
            "dry_run": dry_run,
        }

        if not dry_run and not erros_criticos:
            upload_id = self.db.criar_upload(
                nome_ficheiro, tipo, len(todos_registos), len(todos_avisos)
            )
            if tipo == "batismo":
                self.db.inserir_batismos(todos_registos, upload_id)
            elif tipo == "casamento":
                self.db.inserir_casamentos(todos_registos, upload_id)
            elif tipo == "obito":
                self.db.inserir_obitos(todos_registos, upload_id)
            resumo["upload_id"] = upload_id
            resumo["mensagem"] = f"{len(todos_registos)} registos importados com sucesso."
        elif not dry_run and erros_criticos:
            resumo["sucesso"] = False
            resumo["mensagem"] = "Importação cancelada devido a erros críticos."

        return resumo

    def _processar_folha(self, ws, nome_folha, tipo, mapa, obrigatorios):
        registos = []
        avisos = []
        erros = []

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return registos, avisos, erros

        # Encontrar linha de cabeçalho (primeira linha não vazia)
        cabecalho_idx = None
        cabecalho = []
        for i, row in enumerate(rows):
            valores = [str(v).strip() if v is not None else "" for v in row]
            nao_vazios = [v for v in valores if v]
            if len(nao_vazios) >= 3:
                cabecalho_idx = i
                cabecalho = valores
                break

        if cabecalho_idx is None:
            avisos.append(f"[{nome_folha}] Folha sem cabeçalho reconhecível — ignorada.")
            return registos, avisos, erros

        # Mapear colunas do Excel para campos internos
        indice_campo = {}
        colunas_nao_reconhecidas = []
        for i, col in enumerate(cabecalho):
            col_norm = col.strip()
            if col_norm in mapa:
                indice_campo[mapa[col_norm]] = i
            elif col_norm:
                colunas_nao_reconhecidas.append(col_norm)

        if colunas_nao_reconhecidas:
            avisos.append(
                f"[{nome_folha}] Colunas não reconhecidas (serão ignoradas): "
                + ", ".join(colunas_nao_reconhecidas)
            )

        # Verificar colunas obrigatórias
        for campo in obrigatorios:
            if campo not in indice_campo:
                erros.append(
                    f"[{nome_folha}] Coluna obrigatória em falta: '{campo}'"
                )

        if erros:
            return registos, avisos, erros

        # Processar linhas de dados
        for nr_linha, row in enumerate(rows[cabecalho_idx + 1:], start=cabecalho_idx + 2):
            if all(v is None or str(v).strip() == "" for v in row):
                continue  # linha vazia

            reg = {}
            for campo, idx in indice_campo.items():
                val = row[idx] if idx < len(row) else None
                if campo == "ano":
                    ano, aviso = validar_ano(val)
                    reg["ano"] = ano
                    if aviso:
                        avisos.append(f"[{nome_folha}] Linha {nr_linha}: {aviso}")
                else:
                    reg[campo] = limpar(val)

            # Verificar campos obrigatórios
            for campo in obrigatorios:
                if not reg.get(campo):
                    avisos.append(
                        f"[{nome_folha}] Linha {nr_linha}: campo '{campo}' em falta ou vazio"
                    )

            registos.append(reg)

        return registos, avisos, erros
