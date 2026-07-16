# Registos Paroquiais

Arquivo digital de batismos, casamentos e óbitos com interface de pesquisa pública
e área de administração para importação de ficheiros Excel.

---

## Estrutura do projecto

```
registos-paroquiais/
├── backend/
│   ├── main.py          # API FastAPI + middleware de segurança
│   ├── database.py      # Camada SQLite + pesquisa normalizada
│   ├── importer.py      # Importador Excel com validação
│   ├── parser.py        # Fallback de pesquisa por padrões regex
│   ├── security.py      # Rate limiting, validação de inputs, headers HTTP
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
de IPs externos com erro 403. A verificação é feita nos prefixos
`127.`, `192.168.`, `10.` e `172.`.

Se usar um proxy reverso (ex: nginx), adicione também uma regra para
bloquear o acesso externo a `/admin`:

```nginx
location /admin {
    allow 127.0.0.1;
    allow 192.168.0.0/16;
    allow 10.0.0.0/8;
    deny all;
    proxy_pass http://localhost:8000;
}
```

---

## Variáveis de ambiente

Criar um ficheiro `.env` na raiz do projecto:

```env
ANTHROPIC_API_KEY=sk-ant-...   # Necessário para pesquisa IA (opcional)
DB_PATH=/data/registos.db      # Caminho para a base de dados (default: registos.db)
```

A pesquisa IA fica indisponível sem a chave API — a interface oculta automaticamente
o botão correspondente e o fallback por padrões regex é utilizado no endpoint `/api/pesquisar-ia`.

---

## Importação de dados

1. Aceda a `http://<servidor>/admin` (na rede local)
2. Seleccione o **tipo de registo** (Batismos / Casamentos / Óbitos)
3. Seleccione a **freguesia** (campo com autocomplete com as já importadas)
4. Carregue o ficheiro Excel (.xlsx ou .xls, máx. 50 MB)
5. Clique em **Validar ficheiro** — o sistema analisa todas as folhas
   e apresenta um relatório com:
   - Número de registos encontrados
   - Avisos (campos em falta, anos fora do intervalo esperado, colunas não reconhecidas)
   - Erros críticos (colunas obrigatórias em falta)
6. Se não houver erros críticos, clique em **Importar**

### Notas sobre o Excel
- Cada ficheiro pode ter várias folhas (por exemplo por século: 1700–1799, 1800–1899, etc.)
- Todas as folhas são processadas e importadas de uma vez
- A primeira linha não vazia com 3 ou mais colunas preenchidas é tratada como cabeçalho
- O campo `FONTE` é a referência da fonte (ex: `PT/ADSTR/PRQ/PABT06/002/0011`) — o código
  da parish (`PABT06`) é extraído automaticamente e guardado no registo de upload
- O campo `IDADE/DNASC` é tratado como texto (pode conter idade ou data de nascimento)
- Linhas completamente vazias são ignoradas
- Anos válidos: 1400–2100 (fora deste intervalo gera aviso, mas não bloqueia a importação)

### Colunas esperadas

**Batismos:**
`FONTE (Código de refª)` · `FLS` · `ANO` · `Nº ORDEM` · `NOME` · `DATA NASC` ·
`LOCAL NASCIMENTO` · `PAI` · `MÃE` · `AVÔ PATERNO` · `AVÓ PATERNA` ·
`AVÔ MATERNO` · `AVÓ MATERNA` · `NOTAS`

**Casamentos:**
`FONTE (Código de refª)` · `FLS` · `ANO` · `Nº ORDEM` · `DATA` · `NOIVO` ·
`IDADE/DNASC NOIVO` · `NAT. NOIVO` · `NOIVA` · `IDADE/DNASC NOIVA` · `NAT. NOIVA` ·
`RESID` · `PAI NOIVO` · `NAT PAI Nº` · `MÃE NOIVO` · `NAT MÃE Nº` ·
`PAI NOIVA` · `NAT PAI Nª` · `MÃE NOIVA` · `NAT MÃE Nª` ·
`AVÔ PATERNO Nº` · `AVÓ PATERNA Nº` · `AVÔ MATERNO Nº` · `AVÓ MATERNA Nº` ·
`AVÔ PATERNO Nª` · `AVÓ PATERNA Nª` · `AVÔ MATERNO Nª` · `AVÓ MATERNA Nª` ·
`TESTEMUNHA 1` · `TESTEMUNHA 2` · `NOTAS`

**Óbitos:**
`FONTE (Código de refª)` · `FLS` · `ANO` · `Nº ORDEM` · `NOME` · `DATA ÓBITO` ·
`LOCAL F.` · `IDADE` · `PAI` · `NAT PAI` · `MÃE` · `NAT MÃE` · `NOTAS`

---

## Pesquisa

### Pesquisa simples
A interface pública permite pesquisar por texto livre. A pesquisa é:
- Insensível a maiúsculas e minúsculas
- Insensível a acentos (ex: "Jose" encontra "José")
- Multi-termo com três níveis de relevância:
  1. Frase exacta ("José Alves" encontra "José Alves Bento")
  2. Tokens pela ordem com palavras no meio ("José Alves" encontra "José Maria Alves")
  3. Todos os tokens presentes em qualquer ordem

Campos pesquisados por tipo:
- **Batismos:** nome, pai, mãe, avô/avó paterno/a, avô/avó materno/a
- **Casamentos:** noivo, noiva, pai/mãe do noivo, pai/mãe da noiva, testemunhas
- **Óbitos:** nome, pai, mãe

### Pesquisa IA (linguagem natural)
O botão **✦ Pesquisa IA** envia a query para o Claude Haiku, que extrai campos
estruturados e os traduz em filtros de pesquisa. Exemplos:

| Query | Interpretação |
|---|---|
| `filho de João Frade e Maria Salgueira` | `pai=João Frade, mae=Maria Salgueira` |
| `casamentos da família Silva em 1823` | `tipo=casamento, nome=Silva, ano=1823` |
| `cujo avô paterno era Manuel Costa` | `avo_paterno=Manuel Costa` |
| `neto paterno de António Faria` | `avo_paterno=António Faria` |
| `óbitos no século XIX` | `tipo=obito, ano_min=1800, ano_max=1899` |

O botão é ocultado automaticamente se o endpoint não estiver acessível (fora da rede local
ou sem chave API configurada). Nesse caso, um parser por padrões regex é utilizado como
fallback no servidor.

### Filtros manuais
Combinam com qualquer pesquisa:
- **Tipo:** Batismos / Casamentos / Óbitos
- **Período:** ano mínimo e máximo
- **Fonte:** referência do arquivo (ex: `PT/ADSTR/PRQ/PABT06`)

### Facetas dinâmicas
Após uma pesquisa com mais de um resultado, surge um painel lateral (desktop)
ou drawer (mobile) com filtros adicionais sobre os resultados já obtidos:
- Tipo de registo
- Localidade
- Pai / Mãe
- Período (slider de anos)

A paginação é feita do lado do cliente sobre o conjunto completo de resultados
(até 5000 por pesquisa), com 25 registos por página.

---

## Estatísticas

A vista de estatísticas (separador no cabeçalho) apresenta:
- Totais globais por tipo de registo
- Detalhes por freguesia: totais, intervalos de datas e histórico de importações
- Código do arquivo distrital extraído automaticamente da referência FONTE
- Gráficos de barras com distribuição por década (batismos, casamentos, óbitos)

---

## Segurança

A aplicação implementa um conjunto de controlos de segurança baseados nas recomendações OWASP:

### Rate limiting
Limites por IP com bloqueio automático de 5 minutos após exceder o limite:

| Endpoint | Limite |
|---|---|
| Pesquisa (`/api/pesquisar`, `/api/estatisticas`, etc.) | 60 pedidos/min |
| Pesquisa IA (`/api/pesquisar-ia`) | 10 pedidos/min |
| Upload (`/admin/api/upload`) | 10 pedidos/5 min |
| Admin (outros) | 30 pedidos/min |

### Validação de inputs
- Limite de 500 caracteres por campo
- Detecção de padrões maliciosos: SQL injection, XSS, path traversal, LFI, template injection
- Validação de tipos de registo, anos e números de página

### Validação de ficheiros
- Apenas `.xlsx` e `.xls`
- Tamanho máximo: 50 MB
- Verificação de magic bytes (conteúdo real, não apenas extensão)

### Headers de segurança HTTP
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; …
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

### Auditoria
Todos os acessos são registados na base de dados (excluindo `/static` e `/favicon`).
A área de admin apresenta:
- Acessos por IP (últimos 90 dias): total, pesquisas, acessos admin, primeiro e último acesso
- Actividade diária (últimos 30 dias) com gráfico de barras
- Endpoints mais acedidos
- Eventos suspeitos (status 403, 429, 5xx)

Os registos de auditoria são limpos automaticamente após 90 dias.

### Outros controlos
- Documentação da API (`/docs`, `/redoc`) desactivada
- Área de admin restrita a IPs de rede local
- Logs de segurança com nível WARNING para eventos suspeitos (rate limit, padrões maliciosos, acesso externo a admin)

---

## Interface

### Público
- Barra de estatísticas clicável no topo (filtra directamente por tipo)
- Disclaimer sobre consulta do registo original
- Modal de detalhe com todos os campos organizados por secções
- Destaque dos termos pesquisados nos resultados
- Guia de ajuda integrado com exemplos de pesquisa IA
- Totalmente responsiva: desktop, tablet, mobile (≤640 px e ≤375 px)

### Administração
- Upload com drag & drop e relatório de validação antes de confirmar
- Campo de freguesia com autocomplete (sugere as já importadas)
- Histórico de importações com tipo, período e número de registos
- Reset da base de dados com dupla confirmação
- Painel de auditoria de acessos
