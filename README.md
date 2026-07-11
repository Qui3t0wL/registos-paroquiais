# Registos Paroquiais

Arquivo digital de batismos, casamentos e óbitos com interface de pesquisa pública
e área de administração para importação de ficheiros Excel.

---

## Estrutura do projecto

```
registos-paroquiais/
├── backend/
│   ├── main.py          # API FastAPI
│   ├── database.py      # Camada SQLite
│   ├── importer.py      # Importador Excel com validação
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── public/
│   │   └── index.html   # Interface pública de pesquisa
│   └── admin/
│       └── index.html   # Interface de administração
├── data/                # Criada automaticamente (base de dados)
├── docker-compose.yml
└── README.md
```

---

## Instalação (sem Docker)

### Pré-requisitos
- Python 3.10+

### Passos

```bash
cd backend
pip install -r requirements.txt
python main.py
```

A aplicação fica disponível em `http://localhost:8000`.

---

## Instalação com Docker

```bash
docker compose up -d
```

A aplicação fica disponível em `http://localhost:8000`.

A base de dados é guardada na pasta `data/` do projecto, persistindo entre reinícios.

---

## Configuração de rede

### Interface pública (pesquisa)
Acessível em `http://<ip-do-servidor>:8000`

Para expor à Internet, configure o router para reencaminhar a porta 8000,
ou use um proxy reverso (nginx/Caddy) com HTTPS.

### Interface de administração
Acessível em `http://<ip-do-servidor>:8000/admin`

**Apenas acessível a partir da rede local** — o backend rejeita pedidos
de IPs externos com erro 403.

Se usar um proxy reverso (ex: nginx), adicione também uma regra para
bloquear o acesso externo a `/admin`:

```nginx
# Exemplo nginx
location /admin {
    allow 127.0.0.1;
    allow 192.168.0.0/16;
    allow 10.0.0.0/8;
    deny all;
    proxy_pass http://localhost:8000;
}
```

---

## Importação de dados

1. Aceda a `http://<servidor>/admin` (na rede local)
2. Seleccione o tipo de registo (Batismos / Casamentos / Óbitos)
3. Carregue o ficheiro Excel
4. Clique em **Validar ficheiro** — o sistema analisa todas as folhas
   e apresenta um relatório com:
   - Número de registos encontrados
   - Avisos (campos em falta, anos fora do intervalo esperado, etc.)
   - Erros críticos (colunas obrigatórias em falta)
5. Se não houver erros críticos, clique em **Importar**

### Notas sobre o Excel
- Cada ficheiro pode ter várias folhas (por século: 1700-1799, 1800-1899, etc.)
- Todas as folhas são importadas de uma vez
- O campo FONTE é a referência da fonte (ex: `PT/ADSTR/PRQ/PABT06/002/0011`)
- O campo IDADE/DNASC é tratado como texto (pode conter idade ou data)
- Linhas completamente vazias são ignoradas

### Colunas esperadas

**Batismos:**
`FONTE (Código de refª)` · `FLS` · `ANO` · `Nº ORDEM` · `NOME` · `DATA NASC` ·
`LOCAL NASCIMENTO` · `PAI` · `MÃE` · `AVÔ PATERNO` · `AVÓ PATERNA` ·
`AVÔ MATERNO` · `AVÓ MATERNA` · `NOTAS`

**Casamentos:**
`FONTE (Código de refª)` · `FLS` · `ANO` · `Nº ORDEM` · `DATA` · `NOIVO` ·
`IDADE/DNASC NOIVO` · `NAT. NOIVO` · `NOIVA` · `IDADE/DNASC NOIVA` ·
`NAT. NOIVA` · `LOCAL` · `PAI NOIVO` · `NAT PAI Nº` · `MÃE NOIVO` ·
`NAT MÃE Nº` · `PAI NOIVA` · `NAT PAI Nª` · `MÃE NOIVA` · `NAT MÃE Nª` ·
`TESTEMUNHA 1` · `TESTEMUNHA 2` · `NOTAS`

**Óbitos:**
`FONTE (Código de refª)` · `FLS` · `ANO` · `Nº ORDEM` · `NOME` · `DATA ÓBITO` ·
`LOCAL` · `PAI` · `MÃE` · `NOTAS`

---

## Pesquisa

A interface pública permite pesquisar por:
- **Nome** (e campos de filiação: pai, mãe, avós, testemunhas)
- **Tipo de registo** (batismo / casamento / óbito)
- **Período** (ano mínimo e máximo)
- **Fonte** (referência do arquivo)

A pesquisa por nome é insensível a maiúsculas e suporta múltiplos termos.
