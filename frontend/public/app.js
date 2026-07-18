const API = '';
let paginaAtual = 1;
let dadosEstatisticas = null;
const POR_PAGINA = 25;
let modoFederado = false;
// Estado das facetas
let todosResultados = [];
let facetasActivas  = {};
let anoMinGlobal = 1500, anoMaxGlobal = 2100;
let anoMinActivo = 1500, anoMaxActivo = 2100;

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  await Promise.all([carregarEstatisticas(), carregarFontes(), carregarFooter()]);
  await verificarAcessoIA();
  document.getElementById('campoPesquisa').addEventListener('keydown', e => {
    if (e.key === 'Enter') pesquisar(1);
  });
  window.addEventListener('resize', () => {
    const painel = document.getElementById('painelFacetas');
    const layout = document.getElementById('layoutResultados');
    if (todosResultados.length > 1) {
      if (window.innerWidth > 640) {
        painel.style.display = 'block';
        layout.classList.remove('sem-facetas');
      } else {
        painel.style.display = 'none';
        layout.classList.add('sem-facetas');
      }
    }
  });
  verificarNosFederados();
}

async function carregarFooter() {
  try {
    const r = await fetch(`${API}/api/configuracao/footer`);
    const d = await r.json();
    const el = document.getElementById('footerTexto');
    if (d.footer_texto) {
      // Converter URLs simples em links clicáveis
      el.innerHTML = d.footer_texto.replace(
        /(https?:\/\/[^\s]+)/g,
        '<a href="$1" target="_blank" rel="noopener" style="color:var(--cinza);text-decoration:underline;text-underline-offset:2px">$1</a>'
      );
    }
  } catch(e) {}
}

async function verificarAcessoIA() {
  try {
    const r = await fetch(`${API}/api/pesquisar-ia?q=teste`);
    if (r.status === 403) document.getElementById('btnIA').style.display = 'none';
  } catch(e) {
    document.getElementById('btnIA').style.display = 'none';
  }
}

async function carregarEstatisticas() {
  try {
    const r = await fetch(`${API}/api/estatisticas`);
    dadosEstatisticas = await r.json();
    const fmt = n => (n || 0).toLocaleString('pt-PT');
    document.getElementById('statBatismos').textContent   = fmt(dadosEstatisticas.batismos.total);
    document.getElementById('statCasamentos').textContent = fmt(dadosEstatisticas.casamentos.total);
    document.getElementById('statObitos').textContent     = fmt(dadosEstatisticas.obitos.total);
  } catch(e) {}
}

async function carregarFontes() {
  try {
    const r = await fetch(`${API}/api/fontes`);
    const fontes = await r.json();
    const sel = document.getElementById('filtrFonte');
    fontes.forEach(f => {
      const opt = document.createElement('option');
      opt.value = f; opt.textContent = f;
      sel.appendChild(opt);
    });
  } catch(e) {}
}

// ── Navegação ─────────────────────────────────────────────────────────────────

function mostrarVista(vista) {
  document.getElementById('vistaPesquisa').style.display     = vista === 'pesquisa' ? '' : 'none';
  document.getElementById('vistaEstatisticas').style.display = vista === 'estatisticas' ? '' : 'none';
  document.querySelectorAll('.btn-nav').forEach((b, i) => {
    b.classList.toggle('ativo', (i === 0) === (vista === 'pesquisa'));
  });
  if (vista === 'estatisticas') carregarGraficos();
}

function filtrarTipo(tipo) {
  mostrarVista('pesquisa');
  document.getElementById('filtrTipo').value = tipo;
  pesquisar(1);
}

// ── Verificar se há nós activos (decide se o botão aparece) ──────────────────
async function verificarNosFederados() {
  try {
    const r = await fetch('/api/pesquisar-federado?por_pagina=1');
    const d = await r.json();
    // nos_consultados inclui o local; só mostrar se houver pelo menos 1 remoto
    if ((d.nos_consultados || 1) > 1) {
      document.getElementById('btnFederado').style.display = 'flex';
    }
  } catch(e) {}
}

// ── Toggle do modo federado ───────────────────────────────────────────────────
function toggleFederado() {
  modoFederado = !modoFederado;
  const btn = document.getElementById('btnFederado');
  btn.classList.toggle('activo', modoFederado);
  btn.title = modoFederado
    ? 'A pesquisar em toda a rede — clique para desactivar'
    : 'Pesquisar também noutros arquivos na rede';
  // Refazer a pesquisa com o novo modo se já houver resultados
  if (todosResultados.length > 0 ||
      document.getElementById('campoPesquisa').value.trim()) {
    pesquisar(1);
  }
}

// ── Pesquisa federada (chama o endpoint agregador) ────────────────────────────
async function _fetchFederado(params) {
  const r = await fetch(`/api/pesquisar-federado?${params}`);
  return await r.json();
}

// ── Barra de estado da federação ─────────────────────────────────────────────
function mostrarEstadoFederado(d) {
  const el       = document.getElementById('federadoEstado');
  const nosErro  = d.nos_com_erro || [];
  const nRemoto  = (d.nos_consultados || 1) - 1;
  const nOk      = nRemoto - nosErro.length;

  const chips = [
    `<span class="fed-chip">📖 Este arquivo</span>`,
    ...Array.from({length: nOk}, (_, i) =>
      `<span class="fed-chip">📡 Nó ${i + 1}</span>`),
    ...nosErro.map(n =>
      `<span class="fed-chip erro" title="${n.erro}">✕ ${n.nome}</span>`),
  ].join('');

  el.innerHTML = `
    <span style="color:var(--azul-medio);font-weight:500">📡 Rede</span>
    <span style="color:var(--linha)">·</span>
    ${chips}
    ${nosErro.length
      ? `<span style="font-size:0.7rem">${nosErro.length} nó(s) inacessível(is)</span>`
      : ''}`;
  el.classList.add('visivel');
}

function esconderEstadoFederado() {
  const el = document.getElementById('federadoEstado');
  el.classList.remove('visivel');
  el.innerHTML = '';
}

function _criarCard(reg, q) {
  const card = document.createElement('div');
  card.className = 'card';
  card.dataset.tipo = reg.tipo;

  const tipoLabel = { batismo:'Batismo', casamento:'Casamento', obito:'Óbito' }[reg.tipo];
  const detalhes  = [];
  if (reg.data) detalhes.push(reg.data);
  if (reg.local && reg.local !== 'n/d') detalhes.push(reg.local);
  const pais = [reg.pai, reg.mae].filter(p => p && p !== 'n/d').join(' & ');
  if (pais) detalhes.push(`Fil. ${pais}`);

  const origemHtml = (modoFederado && reg._no && !reg._no.local)
    ? `<div class="card-origem">📡 ${reg._no.nome}</div>`
    : '';

  card.innerHTML = `
    <span class="badge badge-${reg.tipo}">${tipoLabel}</span>
    <div>
      <div class="card-nome">${destacar(reg.nome || '—', q)}</div>
      <div class="card-detalhe">${detalhes.join(' · ')}</div>
      ${origemHtml}
    </div>
    <div class="card-ano">${reg.ano || '—'}</div>`;

  card.addEventListener('click', () => {
    if (modoFederado && reg._no && !reg._no.local) {
      _abrirDetalheRemoto(reg);
    } else {
      abrirDetalhe(reg.tipo, reg.id);
    }
  });
  return card;
}
// ── Detalhe de registo remoto ─────────────────────────────────────────────────
async function _abrirDetalheRemoto(reg) {
  try {
    // Usa o endpoint federado autenticado do nó remoto
    // O token já está guardado no servidor — o nosso backend actua como proxy
    const r = await fetch(
      `${reg._no.url}/api/registo-federado/${reg.tipo}/${reg.id}`,
      // Nota: o token NÃO é enviado pelo browser directamente.
      // Para maior segurança, criar um endpoint proxy no backend local:
      // GET /api/proxy-registo?no_url=...&tipo=...&id=...
      // que adiciona o token server-side. Ver INTEGRACAO.md.
    );
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const dados = await r.json();
    _renderModalRemoto(reg, dados);
  } catch(e) {
    // Fallback: tentar via proxy local
    try {
      const r = await fetch(
        `/api/registo-proxy?url=${encodeURIComponent(reg._no.url)}&tipo=${reg.tipo}&id=${reg.id}`
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const dados = await r.json();
      _renderModalRemoto(reg, dados);
    } catch(e2) {
      alert('Não foi possível carregar o detalhe deste registo.');
    }
  }
}

function _renderModalRemoto(reg, dados) {
  const tipoLabel = { batismo:'Batismo', casamento:'Casamento', obito:'Óbito' }[reg.tipo];
  document.getElementById('modalTipoBadge').innerHTML = `
    <span class="badge badge-${reg.tipo}">${tipoLabel}</span>
    <span style="font-size:0.68rem;color:var(--texto-sub);margin-left:0.4rem">
      📡 ${reg._no?.nome || reg._no?.url}
    </span>`;

  let titulo = reg.tipo === 'casamento'
    ? `${dados.noivo || '—'} & ${dados.noiva || '—'}`
    : (dados.nome || '—');
  if (dados.ano) titulo += ` · ${dados.ano}`;
  document.getElementById('modalTitulo').textContent = titulo;

  const corpo = document.getElementById('modalCorpo');
  corpo.innerHTML = '';
  (SECOES[reg.tipo] || []).forEach(secao => {
    const campos = secao.campos.filter(({ c }) => dados[c] && dados[c] !== 'n/d');
    if (!campos.length) return;
    const secDiv = document.createElement('div');
    secDiv.className = 'modal-secao';
    secDiv.innerHTML = `<div class="modal-secao-titulo">${secao.titulo}</div>`;
    const grid = document.createElement('div');
    grid.className = 'modal-grid';
    campos.forEach(({ c, l, largo }) => {
      const div = document.createElement('div');
      div.className = `modal-campo${largo ? ' largo' : ''}`;
      div.innerHTML = `<label>${l}</label><span>${dados[c]}</span>`;
      grid.appendChild(div);
    });
    secDiv.appendChild(grid);
    corpo.appendChild(secDiv);
  });

  // Rodapé com origem
  const nota = document.createElement('div');
  nota.className = 'modal-origem';
  nota.innerHTML = `📡 Registo proveniente de
    <a href="${reg._no.url}" target="_blank" rel="noopener">${reg._no.nome}</a>`;
  corpo.appendChild(nota);

  document.getElementById('overlay').classList.add('aberto');
  document.body.style.overflow = 'hidden';
}
  
// ── Estatísticas ──────────────────────────────────────────────────────────────

async function carregarGraficos() {
  const cont = document.getElementById('conteudoEstatisticas');
  try {
    const [rFreg, rDet] = await Promise.all([
      fetch(`${API}/api/estatisticas-freguesias`),
      fetch(`${API}/api/estatisticas-detalhadas`),
    ]);
    const freguesias = await rFreg.json();
    const detalhadas = await rDet.json();
    renderEstatisticas(freguesias, detalhadas);
  } catch(e) {
    cont.innerHTML = '<div class="estado"><p>Erro ao carregar estatísticas.</p></div>';
  }
}

function renderEstatisticas(freguesias, detalhadas) {
  const cont = document.getElementById('conteudoEstatisticas');
  const totalB = dadosEstatisticas?.batismos?.total || 0;
  const totalC = dadosEstatisticas?.casamentos?.total || 0;
  const totalO = dadosEstatisticas?.obitos?.total || 0;
  const totalGeral = totalB + totalC + totalO;

  cont.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin-bottom:1.5rem" class="stats-resumo-global">
      ${[
        { label: 'Total de registos', valor: totalGeral, cor: 'var(--azul-escuro)' },
        { label: 'Batismos',   valor: totalB, cor: 'var(--batismo)' },
        { label: 'Casamentos', valor: totalC, cor: 'var(--casamento)' },
        { label: 'Óbitos',     valor: totalO, cor: 'var(--obito)' },
      ].map(s => `
        <div class="stats-card" style="text-align:center;padding:1rem">
          <div style="font-size:1.6rem;font-weight:700;color:${s.cor}">${s.valor.toLocaleString('pt-PT')}</div>
          <div style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.07em;color:var(--texto-sub);margin-top:0.3rem">${s.label}</div>
        </div>
      `).join('')}
    </div>

    ${freguesias.length === 0
      ? '<div class="estado"><p>Sem dados de freguesias disponíveis.</p></div>'
      : freguesias.map(f => renderFreguesia(f)).join('')}

    <div style="margin-top:1.5rem">
      <div style="font-size:0.75rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--texto-sub);margin-bottom:1rem">Distribuição por década</div>
      <div class="stats-grid">
        <div class="stats-card">
          <div class="stats-card-titulo"><span class="stat-dot" style="background:var(--batismo)"></span>Batismos</div>
          <div class="grafico-barras" id="grafBatismos"></div>
        </div>
        <div class="stats-card">
          <div class="stats-card-titulo"><span class="stat-dot" style="background:var(--casamento)"></span>Casamentos</div>
          <div class="grafico-barras" id="grafCasamentos"></div>
        </div>
        <div class="stats-card">
          <div class="stats-card-titulo"><span class="stat-dot" style="background:var(--obito)"></span>Óbitos</div>
          <div class="grafico-barras" id="grafObitos"></div>
        </div>
      </div>
    </div>
  `;

  renderGrafico('grafBatismos',   detalhadas.batismos_por_decada,   'barra-batismo');
  renderGrafico('grafCasamentos', detalhadas.casamentos_por_decada, 'barra-casamento');
  renderGrafico('grafObitos',     detalhadas.obitos_por_decada,     'barra-obito');
}

function renderFreguesia(f) {
  const tipos = {
    batismos:   { label: 'Batismos',   cor: 'var(--batismo)' },
    casamentos: { label: 'Casamentos', cor: 'var(--casamento)' },
    obitos:     { label: 'Óbitos',     cor: 'var(--obito)' },
  };
  const resumoTipos = Object.entries(tipos).map(([key, cfg]) => {
    const d = f.tipos[key];
    if (!d) return '';
    return `
      <div style="display:flex;flex-direction:column;gap:0.15rem">
        <div style="font-size:0.65rem;font-weight:600;letter-spacing:0.07em;text-transform:uppercase;color:${cfg.cor}">${cfg.label}</div>
        <div style="font-size:1.1rem;font-weight:700;color:var(--texto)">${d.total.toLocaleString('pt-PT')}</div>
        <div style="font-size:0.72rem;color:var(--texto-sub)">${d.ano_min} – ${d.ano_max}</div>
      </div>`;
  }).join('');

  const uploadsHtml = f.uploads.map(u => {
    const tipoLabel = { batismo:'Batismos', casamento:'Casamentos', obito:'Óbitos' }[u.tipo] || u.tipo;
    const dataHora  = u.data_upload?.substring(0,16).replace('T',' ') || '—';
    const periodo   = u.ano_min && u.ano_max ? `${u.ano_min} – ${u.ano_max}` : u.ano_min || u.ano_max || '—';
    return `
      <div style="display:grid;grid-template-columns:130px auto 1fr auto;gap:0.5rem;align-items:center;padding:0.5rem 0;border-bottom:1px solid var(--linha);font-size:0.78rem">
        <span style="color:var(--texto-sub)">${dataHora}</span>
        <span class="badge badge-${u.tipo}" style="font-size:0.6rem">${tipoLabel}</span>
        <span style="color:var(--texto-sub);font-size:0.72rem">${periodo}</span>
        <span style="font-weight:600;text-align:right">${u.registos.toLocaleString('pt-PT')}</span>
      </div>`;
  }).join('');

  return `
    <div class="stats-card" style="margin-bottom:1rem">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:1rem;padding-bottom:0.8rem;border-bottom:1px solid var(--linha)">
        <div>
          <div style="font-size:1rem;font-weight:600;color:var(--texto)">${f.nome}</div>
          ${f.codigo_adist ? `<div style="font-size:0.72rem;color:var(--texto-sub);margin-top:0.2rem;font-family:monospace">${f.codigo_adist}</div>` : ''}
        </div>
        <div style="font-size:0.65rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--texto-sub)">
          ${f.uploads.length} ${f.uploads.length !== 1 ? 'importações' : 'importação'}
        </div>
      </div>
      <div style="display:flex;gap:2rem;margin-bottom:1rem;flex-wrap:wrap">${resumoTipos}</div>
      ${f.uploads.length > 0 ? `
        <div style="font-size:0.65rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--texto-sub);margin-bottom:0.4rem">Histórico de importações</div>
        ${uploadsHtml}` : ''}
    </div>`;
}

function renderGrafico(containerId, dados, classeBarrra) {
  const cont = document.getElementById(containerId);
  if (!dados || dados.length === 0) {
    cont.innerHTML = '<p style="color:var(--texto-sub);font-size:0.8rem;padding:0.5rem 0">Sem dados</p>';
    return;
  }
  const max = Math.max(...dados.map(d => d.total));
  cont.innerHTML = dados.map(d => `
    <div class="barra-linha">
      <div class="barra-label">${d.decada}s</div>
      <div class="barra-track">
        <div class="barra-fill ${classeBarrra}" style="width:${max ? (d.total/max*100) : 0}%"></div>
      </div>
      <div class="barra-valor">${d.total.toLocaleString('pt-PT')}</div>
    </div>`).join('');
}

// ── Pesquisa ──────────────────────────────────────────────────────────────────

async function pesquisar(pagina) {
  paginaAtual = pagina || 1;
  esconderInterpretacao();

  const q      = document.getElementById('campoPesquisa').value.trim();
  const tipo   = document.getElementById('filtrTipo').value;
  const anoMin = document.getElementById('filtrAnoMin').value;
  const anoMax = document.getElementById('filtrAnoMax').value;
  const fonte  = document.getElementById('filtrFonte').value;

  const params = new URLSearchParams({ pagina: 1, por_pagina: 5000 });
  if (q)      params.set('q', q);
  if (tipo)   params.set('tipo', tipo);
  if (anoMin) params.set('ano_min', anoMin);
  if (anoMax) params.set('ano_max', anoMax);
  if (fonte)  params.set('fonte', fonte);

  mostrarCarregando();

  try {
    let d;
    if (modoFederado) {
      // Limitar por_pagina no modo federado (agrega de vários nós)
      params.set('por_pagina', 200);
      d = await _fetchFederado(params);
      mostrarEstadoFederado(d);
    } else {
      const r = await fetch(`${API}/api/pesquisar?${params}`);
      d = await r.json();
      esconderEstadoFederado();
    }

    todosResultados = d.resultados;
    facetasActivas  = {};
    anoMinActivo    = 1500;
    anoMaxActivo    = 2100;
    renderResultados(d, q);
  } catch(e) {
    document.getElementById('listaResultados').innerHTML =
      `<div class="estado"><div class="estado-icon">⚠</div><p>Erro ao contactar o servidor.</p></div>`;
  }
}

async function pesquisarIA(pagina) {
  const q = document.getElementById('campoPesquisa').value.trim();
  if (!q) { document.getElementById('campoPesquisa').focus(); return; }
  paginaAtual = 1;
  mostrarCarregando();
  esconderInterpretacao();
  try {
    const params = new URLSearchParams({ q, pagina: 1, por_pagina: 5000 });
    const r = await fetch(`${API}/api/pesquisar-ia?${params}`);
    const d = await r.json();
    if (!r.ok) {
      document.getElementById('listaResultados').innerHTML =
        `<div class="estado"><div class="estado-icon">⚠</div><p>${d.detail || 'Erro na pesquisa IA.'}</p></div>`;
      return;
    }
    todosResultados = d.resultados;
    facetasActivas  = {};
    anoMinActivo    = 1500;
    anoMaxActivo    = 2100;
    mostrarInterpretacao(d.interpretacao, d.usou_ia);
    renderResultados(d, '');
  } catch(e) {
    document.getElementById('listaResultados').innerHTML =
      `<div class="estado"><div class="estado-icon">⚠</div><p>Erro ao contactar o servidor.</p></div>`;
  }
}

function mostrarInterpretacao(filtros, usouIA) {
  if (!filtros || Object.keys(filtros).length === 0) return;
  const etiquetas = {
    nome:'Nome', pai:'Pai', mae:'Mãe', noivo:'Noivo', noiva:'Noiva',
    testemunha:'Testemunha', local:'Local', tipo:'Tipo',
    fonte:'Fonte', ano_min:'De', ano_max:'Até' /* alterei o 'Desde' para 'De' */
  };
  const chips = Object.entries(filtros)
    .map(([k,v]) => `<span class="ia-chip"><span>${etiquetas[k]||k}:</span>${v}</span>`)
    .join('');
  const modo = usouIA
    ? '<span style="color:var(--laranja);font-weight:600">✦ IA</span> interpretou:'
    : '<span style="color:var(--texto-sub)">Padrões</span> interpretaram:';
  const el = document.getElementById('iaInterpretacao');
  el.innerHTML = `${modo} ${chips}`;
  if (!usouIA) el.innerHTML += `<span class="ia-fallback">(API IA indisponível)</span>`;
  el.classList.add('visivel');
}

function esconderInterpretacao() {
  const el = document.getElementById('iaInterpretacao');
  el.classList.remove('visivel');
  el.innerHTML = '';
}

// ── Render ────────────────────────────────────────────────────────────────────

function mostrarCarregando() {
  document.getElementById('infoResultados').style.display = 'none';
  document.getElementById('listaResultados').innerHTML =
    `<div class="estado"><p>A pesquisar…</p></div>`;
  document.getElementById('paginacao').innerHTML = '';
}

function renderResultados(d, q) {
  const info      = document.getElementById('infoResultados');
  const layout    = document.getElementById('layoutResultados');
  const painel    = document.getElementById('painelFacetas');
  const btnMobile = document.getElementById('btnFiltrarMobile');

  if (d.total === 0) {
    document.getElementById('listaResultados').innerHTML =
      `<div class="estado"><div class="estado-icon">🔍</div>
       <p>Nenhum registo encontrado${q ? ` para "<strong>${q}</strong>"` : ''}.</p></div>`;
    info.style.display = 'none';
    painel.style.display = 'none';
    layout.classList.add('sem-facetas');
    btnMobile.style.display = 'none';
    document.getElementById('paginacao').innerHTML = '';
    return;
  }

  if (d.total > 1) {
    if (window.innerWidth > 640) {
      painel.style.display = 'block';
      layout.classList.remove('sem-facetas');
    } else {
      painel.style.display = 'none';
      layout.classList.add('sem-facetas');
    }
    btnMobile.style.display = 'flex';
    renderFacetas(todosResultados);
  }

  info.style.display = 'flex';
  aplicarFacetas();
}

function renderCards(resultados) {
  const lista = document.getElementById('listaResultados');
  if (!resultados.length) {
    lista.innerHTML = `<div class="estado"><div class="estado-icon">🔍</div>
      <p>Nenhum resultado com os filtros seleccionados.</p></div>`;
    return;
  }

  const q = document.getElementById('campoPesquisa').value.trim();
  lista.innerHTML = '';

  if (modoFederado) {
    // Agrupar por arquivo de origem
    const grupos = new Map();
    resultados.forEach(r => {
      const chave = r._no?.url || 'local';
      if (!grupos.has(chave)) grupos.set(chave, { no: r._no, items: [] });
      grupos.get(chave).items.push(r);
    });

    grupos.forEach(({ no, items }) => {
      const isLocal = no?.local ?? true;
      const sep = document.createElement('div');
      sep.className = 'grupo-origem';
      sep.innerHTML = `
        <span class="grupo-origem-dot"
              style="background:${isLocal ? 'var(--laranja)' : 'var(--azul-medio)'}"></span>
        ${no?.nome || 'Este arquivo'}
        <span style="font-weight:400;color:var(--texto-sub)">(${items.length})</span>
        ${!isLocal && no?.url
          ? `<a href="${no.url}" target="_blank" rel="noopener"
               style="margin-left:auto;font-size:0.65rem;color:var(--azul-medio);
                      text-decoration:none;opacity:0.7"
               onclick="event.stopPropagation()">↗ visitar</a>`
          : ''}`;
      lista.appendChild(sep);
      items.forEach(reg => lista.appendChild(_criarCard(reg, q)));
    });
  } else {
    resultados.forEach(reg => lista.appendChild(_criarCard(reg, q)));
  }
}
  
function destacar(texto, q) {
  if (!q || !texto) return texto;
  const termos = q.trim().split(/\s+/).map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  return texto.replace(new RegExp(`(${termos.join('|')})`, 'gi'),
    '<mark style="background:#fde8a0;padding:0 1px;border-radius:2px">$1</mark>');
}

// ── Facetas ───────────────────────────────────────────────────────────────────

function calcularFacetas(resultados) {
  const facetas = { tipo:{}, local:{}, pai:{}, mae:{} };
  resultados.forEach(r => {
    facetas.tipo[r.tipo] = (facetas.tipo[r.tipo] || 0) + 1;
    if (r.local && r.local !== 'n/d') facetas.local[r.local] = (facetas.local[r.local] || 0) + 1;
    if (r.pai   && r.pai   !== 'n/d') facetas.pai[r.pai]     = (facetas.pai[r.pai]     || 0) + 1;
    if (r.mae   && r.mae   !== 'n/d') facetas.mae[r.mae]     = (facetas.mae[r.mae]     || 0) + 1;
  });
  return facetas;
}

function renderFacetas(resultados) {
  const facetas = calcularFacetas(resultados);
  const anos = resultados.map(r => r.ano).filter(Boolean);
  anoMinGlobal = anos.length ? Math.min(...anos) : 1500;
  anoMaxGlobal = anos.length ? Math.max(...anos) : 2100;
  if (anoMinActivo === 1500) anoMinActivo = anoMinGlobal;
  if (anoMaxActivo === 2100) anoMaxActivo = anoMaxGlobal;

  const tipoLabels = { batismo:'Batismo', casamento:'Casamento', obito:'Óbito' };
  const grupos = [
    { id:'tipo',  titulo:'Tipo de registo', items: Object.entries(facetas.tipo).sort((a,b)=>b[1]-a[1]).map(([k,v])=>({valor:k, label:tipoLabels[k]||k, count:v})) },
    { id:'local', titulo:'Localidade',      items: Object.entries(facetas.local).sort((a,b)=>b[1]-a[1]).slice(0,20).map(([k,v])=>({valor:k, label:k, count:v})) },
    { id:'pai',   titulo:'Pai',             items: Object.entries(facetas.pai).sort((a,b)=>b[1]-a[1]).slice(0,20).map(([k,v])=>({valor:k, label:k, count:v})) },
    { id:'mae',   titulo:'Mãe',             items: Object.entries(facetas.mae).sort((a,b)=>b[1]-a[1]).slice(0,20).map(([k,v])=>({valor:k, label:k, count:v})) },
  ]; /*alterei todas as slices para terem 20 resultados. Antes tinham 15,10,10 */

  const html = `
    <div class="faceta-grupo">
      <div class="faceta-titulo" onclick="toggleFaceta('anos')">
        Período <span class="faceta-titulo-seta fechado" id="seta-anos">▾</span>
      </div>
      <div class="faceta-lista fechada" id="lista-anos">
        <div class="faceta-slider">
          <div class="faceta-slider-vals">
            <span id="sliderMinVal">${anoMinActivo}</span>
            <span id="sliderMaxVal">${anoMaxActivo}</span>
          </div>
          <input type="range" id="sliderMin" min="${anoMinGlobal}" max="${anoMaxGlobal}" value="${anoMinActivo}" oninput="actualizarSlider('min',this.value)">
          <input type="range" id="sliderMax" min="${anoMinGlobal}" max="${anoMaxGlobal}" value="${anoMaxActivo}" oninput="actualizarSlider('max',this.value)">
        </div>
      </div>
    </div>
    ${grupos.map(g => g.items.length === 0 ? '' : `
      <div class="faceta-grupo">
        <div class="faceta-titulo" onclick="toggleFaceta('${g.id}')">
          ${g.titulo} <span class="faceta-titulo-seta fechado" id="seta-${g.id}">▾</span>
        </div>
        <div class="faceta-lista fechada" id="lista-${g.id}">
          ${g.items.map(item => {
            const activo = (facetasActivas[g.id] || new Set()).has(item.valor);
            return `<label class="faceta-item ${activo?'activo':''}">
              <input type="checkbox" ${activo?'checked':''} onchange="toggleFiltro('${g.id}','${item.valor.replace(/'/g,"\\'")}')">
              <span class="faceta-item-label" title="${item.label}">${item.label}</span>
              <span class="faceta-item-count">${item.count}</span>
            </label>`;
          }).join('')}
        </div>
      </div>`).join('')}`;

  document.getElementById('facetasConteudo').innerHTML = html;
  document.getElementById('facetasDrawer').innerHTML   = html;
}

function toggleFaceta(id) {
  ['', 'Drawer'].forEach(suffix => {
    const cont = suffix ? document.getElementById('facetasDrawer') : null;
    const lista = cont ? cont.querySelector(`#lista-${id}`) : document.getElementById(`lista-${id}`);
    const seta  = cont ? cont.querySelector(`#seta-${id}`)  : document.getElementById(`seta-${id}`);
    if (lista) lista.classList.toggle('fechada');
    if (seta)  seta.classList.toggle('fechado');
  });
}

function toggleFiltro(grupo, valor) {
  if (!facetasActivas[grupo]) facetasActivas[grupo] = new Set();
  const s = facetasActivas[grupo];
  if (s.has(valor)) s.delete(valor); else s.add(valor);
  if (s.size === 0) delete facetasActivas[grupo];
  paginaAtual = 1;
  aplicarFacetas();
}

function actualizarSlider(tipo, val) {
  val = parseInt(val);
  if (tipo === 'min') anoMinActivo = Math.min(val, anoMaxActivo);
  else                anoMaxActivo = Math.max(val, anoMinActivo);
  document.getElementById('sliderMinVal').textContent = anoMinActivo;
  document.getElementById('sliderMaxVal').textContent = anoMaxActivo;
  document.getElementById('sliderMin').value = anoMinActivo;
  document.getElementById('sliderMax').value = anoMaxActivo;
  paginaAtual = 1;
  aplicarFacetas();
}

function aplicarFacetas() {
  let filtrados = todosResultados.filter(r => {
    const ano = r.ano || 0;
    if (ano && (ano < anoMinActivo || ano > anoMaxActivo)) return false;
    for (const [grupo, valores] of Object.entries(facetasActivas)) {
      if (valores.size === 0) continue;
      let match = false;
      if (grupo === 'tipo')  match = valores.has(r.tipo);
      if (grupo === 'local') match = valores.has(r.local);
      if (grupo === 'pai')   match = valores.has(r.pai);
      if (grupo === 'mae')   match = valores.has(r.mae);
      if (!match) return false;
    }
    return true;
  });

  const nFiltros = Object.values(facetasActivas).reduce((s,v) => s + v.size, 0)
    + (anoMinActivo > anoMinGlobal || anoMaxActivo < anoMaxGlobal ? 1 : 0);
  const badge = document.getElementById('badgeFiltros');
  badge.textContent    = nFiltros;
  badge.style.display  = nFiltros > 0 ? 'inline' : 'none';

  const total   = filtrados.length;
  const totalOr = todosResultados.length;
  const inicio  = (paginaAtual - 1) * POR_PAGINA + 1;
  const fim     = Math.min(paginaAtual * POR_PAGINA, total);
  const info    = document.getElementById('infoResultados');
  info.style.display = total > 0 ? 'flex' : 'none';
  document.getElementById('textoResultados').textContent = total === totalOr
    ? `${inicio} – ${fim} de ${total.toLocaleString('pt-PT')} registos`
    : `${inicio} – ${fim} de ${total.toLocaleString('pt-PT')} filtrados (${totalOr.toLocaleString('pt-PT')} no total)`;
  document.getElementById('textoFiltrados').style.display = 'none';

  renderCards(filtrados.slice((paginaAtual-1)*POR_PAGINA, paginaAtual*POR_PAGINA));
  renderPaginacaoCliente(total);
  renderFacetas(todosResultados);
}

function limparFacetas() {
  facetasActivas = {};
  anoMinActivo   = anoMinGlobal;
  anoMaxActivo   = anoMaxGlobal;
  paginaAtual    = 1;
  aplicarFacetas();
}

function renderPaginacaoCliente(total) {
  const cont     = document.getElementById('paginacao');
  const nPaginas = Math.ceil(total / POR_PAGINA);
  if (nPaginas <= 1) { cont.innerHTML = ''; return; }
  const atual   = paginaAtual;
  const paginas = [1];
  if (atual > 3) paginas.push('...');
  for (let p = Math.max(2, atual-1); p <= Math.min(nPaginas-1, atual+1); p++) paginas.push(p);
  if (atual < nPaginas-2) paginas.push('...');
  if (nPaginas > 1) paginas.push(nPaginas);
  cont.innerHTML = paginas.map(p =>
    p === '...'
      ? `<span style="padding:0.35rem 0.3rem;color:var(--cinza)">…</span>`
      : `<button class="btn-pag ${p===atual?'ativo':''}" onclick="mudarPagina(${p})">${p}</button>`
  ).join('');
}

function mudarPagina(p) {
  paginaAtual = p;
  aplicarFacetas();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Drawer mobile ─────────────────────────────────────────────────────────────

function abrirDrawer() {
  document.getElementById('drawerOverlay').classList.add('aberto');
  document.getElementById('drawer').classList.add('aberto');
  document.body.style.overflow = 'hidden';
}

function fecharDrawer() {
  document.getElementById('drawerOverlay').classList.remove('aberto');
  document.getElementById('drawer').classList.remove('aberto');
  document.body.style.overflow = '';
}

// ── Modal de detalhe ──────────────────────────────────────────────────────────

const SECOES = {
  batismo: [
    { titulo: 'Identificação', campos: [
      {c:'nome',l:'Nome'},{c:'data_nasc',l:'Data de nascimento'},
      {c:'local_nascimento',l:'Local de nascimento'},{c:'ano',l:'Ano'},
      {c:'nr_ordem',l:'Nº de ordem'},{c:'fls',l:'Fólios'},{c:'fonte',l:'Fonte',largo:true},
    ]},
    { titulo: 'Filiação', campos: [
      {c:'pai',l:'Pai'},{c:'mae',l:'Mãe'},
      {c:'avo_paterno',l:'Avô paterno'},{c:'avo_paterna',l:'Avó paterna'},
      {c:'avo_materno',l:'Avô materno'},{c:'avo_materna',l:'Avó materna'},
    ]},
    { titulo: 'Notas', campos: [{c:'notas',l:'Notas',largo:true}] },
  ],
  casamento: [
    { titulo: 'Identificação', campos: [
      {c:'data',l:'Data'},{c:'residencia',l:'Residência'},
      {c:'ano',l:'Ano'},{c:'nr_ordem',l:'Nº de ordem'},
      {c:'fls',l:'Fólios'},{c:'fonte',l:'Fonte',largo:true},
    ]},
    { titulo: 'Noivo', campos: [
      {c:'noivo',l:'Nome'},{c:'idade_dnasc_noivo',l:'Idade / D. Nasc.'},
      {c:'nat_noivo',l:'Naturalidade'},
      {c:'pai_noivo',l:'Pai'},{c:'nat_pai_noivo',l:'Nat. pai'},
      {c:'mae_noivo',l:'Mãe'},{c:'nat_mae_noivo',l:'Nat. mãe'},
      {c:'avo_paterno_noivo',l:'Avô paterno'},{c:'avo_paterna_noivo',l:'Avó paterna'},
      {c:'avo_materno_noivo',l:'Avô materno'},{c:'avo_materna_noivo',l:'Avó materna'},
    ]},
    { titulo: 'Noiva', campos: [
      {c:'noiva',l:'Nome'},{c:'idade_dnasc_noiva',l:'Idade / D. Nasc.'},
      {c:'nat_noiva',l:'Naturalidade'},
      {c:'pai_noiva',l:'Pai'},{c:'nat_pai_noiva',l:'Nat. pai'},
      {c:'mae_noiva',l:'Mãe'},{c:'nat_mae_noiva',l:'Nat. mãe'},
      {c:'avo_paterno_noiva',l:'Avô paterno'},{c:'avo_paterna_noiva',l:'Avó paterna'},
      {c:'avo_materno_noiva',l:'Avô materno'},{c:'avo_materna_noiva',l:'Avó materna'},
    ]},
    { titulo: 'Testemunhas & Notas', campos: [
      {c:'testemunha1',l:'Testemunha 1'},{c:'testemunha2',l:'Testemunha 2'},
      {c:'notas',l:'Notas',largo:true},
    ]},
  ],
  obito: [
    { titulo: 'Identificação', campos: [
      {c:'nome',l:'Nome'},{c:'data_obito',l:'Data de óbito'},
      {c:'local_falecimento',l:'Local de falecimento'},{c:'idade',l:'Idade'},
      {c:'ano',l:'Ano'},{c:'nr_ordem',l:'Nº de ordem'},
      {c:'fls',l:'Fólios'},{c:'fonte',l:'Fonte',largo:true},
    ]},
    { titulo: 'Filiação', campos: [
      {c:'pai',l:'Pai'},{c:'nat_pai',l:'Naturalidade (pai)'},
      {c:'mae',l:'Mãe'},{c:'nat_mae',l:'Naturalidade (mãe)'},
    ]},
    { titulo: 'Notas', campos: [{c:'notas',l:'Notas',largo:true}] },
  ],
};

async function abrirDetalhe(tipo, id) {
  try {
    const r   = await fetch(`${API}/api/registo/${tipo}/${id}`);
    const reg = await r.json();
    const tipoLabel  = { batismo:'Batismo', casamento:'Casamento', obito:'Óbito' }[tipo];
    document.getElementById('modalTipoBadge').innerHTML =
      `<span class="badge badge-${tipo}">${tipoLabel}</span>`;
    let titulo = tipo === 'casamento'
      ? `${reg.noivo||'—'} & ${reg.noiva||'—'}`
      : (reg.nome || '—');
    if (reg.ano) titulo += ` · ${reg.ano}`;
    document.getElementById('modalTitulo').textContent = titulo;
    const corpo = document.getElementById('modalCorpo');
    corpo.innerHTML = '';
    (SECOES[tipo] || []).forEach(secao => {
      const campos = secao.campos.filter(({c}) => reg[c] && reg[c] !== 'n/d');
      if (campos.length === 0) return;
      const secDiv = document.createElement('div');
      secDiv.className = 'modal-secao';
      secDiv.innerHTML = `<div class="modal-secao-titulo">${secao.titulo}</div>`;
      const grid = document.createElement('div');
      grid.className = 'modal-grid';
      campos.forEach(({c, l, largo}) => {
        const div = document.createElement('div');
        div.className = `modal-campo${largo?' largo':''}`;
        div.innerHTML = `<label>${l}</label><span>${reg[c]}</span>`;
        grid.appendChild(div);
      });
      secDiv.appendChild(grid);
      corpo.appendChild(secDiv);
    });
    document.getElementById('overlay').classList.add('aberto');
    document.body.style.overflow = 'hidden';
  } catch(e) {}
}

function fecharModal(e) {
  if (e && e.target !== document.getElementById('overlay')) return;
  document.getElementById('overlay').classList.remove('aberto');
  document.body.style.overflow = '';
}

// ── Ajuda ─────────────────────────────────────────────────────────────────────

function abrirAjuda() {
  document.getElementById('overlayAjuda').classList.add('aberto');
  document.body.style.overflow = 'hidden';
}

function fecharAjuda(e) {
  if (e && e.target !== document.getElementById('overlayAjuda')) return;
  document.getElementById('overlayAjuda').classList.remove('aberto');
  document.body.style.overflow = '';
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    fecharModal({ target: document.getElementById('overlay') });
    fecharAjuda({ target: document.getElementById('overlayAjuda') });
    fecharDrawer();
  }
});

// ── Utilitários ───────────────────────────────────────────────────────────────

function limparFiltros() {
  ['campoPesquisa','filtrAnoMin','filtrAnoMax'].forEach(id => document.getElementById(id).value = '');
  ['filtrTipo','filtrFonte'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('listaResultados').innerHTML = '';
  document.getElementById('infoResultados').style.display = 'none';
  document.getElementById('paginacao').innerHTML = '';
  esconderInterpretacao();
  limparFacetas();
}

init();
