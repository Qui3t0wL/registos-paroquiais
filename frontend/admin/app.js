let ficheiroAtual = null;
let dadosValidacao = null;
let todasFreguesias = [];

const FOOTER_DEFAULT = 'Exclusão de responsabilidade: A informação disponível nesta plataforma foi recolhida a partir de registos paroquiais disponíveis online em https://digitarq.arquivos.pt. É possível que existam eventuais erros de transcrição.';
const FOOTER_MAX     = 2000;

async function carregarFreguesias() {
  try {
    const r = await fetch('/admin/api/freguesias');
    todasFreguesias = await r.json();
  } catch(e) {}
}

function filtrarFreguesias(val) {
  const sugestoes = val
    ? todasFreguesias.filter(f => f.toLowerCase().includes(val.toLowerCase()))
    : todasFreguesias;
  renderSugestoes(sugestoes);
}

function mostrarSugestoes() {
  renderSugestoes(todasFreguesias);
}

function ocultarSugestoes() {
  document.getElementById('sugestoesFreguesia').style.display = 'none';
}

function renderSugestoes(lista) {
  const cont = document.getElementById('sugestoesFreguesia');
  if (!lista.length) { cont.style.display = 'none'; return; }
  cont.innerHTML = lista.map(f => `
    <div onclick="seleccionarFreguesia('${f}')"
         style="padding:0.5rem 0.8rem;cursor:pointer;font-size:0.85rem;
                border-bottom:1px solid var(--linha)"
         onmouseover="this.style.background='var(--bg3)'"
         onmouseout="this.style.background=''">
      ${f}
    </div>
  `).join('');
  cont.style.display = 'block';
}

function seleccionarFreguesia(nome) {
  document.getElementById('inputFreguesia').value = nome;
  ocultarSugestoes();
}
// ── Drag & drop ──────────────────────────────────────────────────────────────

const zona = document.getElementById('zonaDrop');
zona.addEventListener('dragover', e => { e.preventDefault(); zona.classList.add('dragover'); });
zona.addEventListener('dragleave', () => zona.classList.remove('dragover'));
zona.addEventListener('drop', e => {
  e.preventDefault();
  zona.classList.remove('dragover');
  const f = e.dataTransfer.files[0];
  if (f) definirFicheiro(f);
});

function ficheirSelecionado(input) {
  if (input.files[0]) definirFicheiro(input.files[0]);
}

function definirFicheiro(f) {
  if (!f.name.match(/\.(xlsx|xls)$/i)) {
    mostrarAlerta('erro', 'Por favor seleccione um ficheiro .xlsx ou .xls.');
    return;
  }
  ficheiroAtual = f;
  document.getElementById('nomeFile').textContent = f.name;
  document.getElementById('nomeFile').style.display = 'block';
  document.getElementById('btnValidar').disabled = false;
  document.getElementById('relatorio').style.display = 'none';
  dadosValidacao = null;
  esconderAlerta();
}

// ── Validação ────────────────────────────────────────────────────────────────

async function validar() {
  if (!ficheiroAtual) return;
  const tipo = document.getElementById('tipoRegisto').value;
  const freguesia = document.getElementById('inputFreguesia').value.trim();
  const btn = document.getElementById('btnValidar');
	const modoAct = document.getElementById('modoActualizacao').checked;
	const params = new URLSearchParams({ tipo });
	if (freguesia) params.set('freguesia', freguesia);
	if (modoAct)   params.set('modo_actualizacao', 'true');
  btn.disabled = true;
  btn.textContent = 'A validar…';
  try {
    const form = new FormData();
    form.append('ficheiro', ficheiroAtual);
    const params = new URLSearchParams({ tipo });
    if (freguesia) params.set('freguesia', freguesia);
    const r = await fetch(`/admin/api/upload?${params}`, { method: 'POST', body: form });
    dadosValidacao = await r.json();
    renderRelatorio(dadosValidacao, tipo);
  } catch(e) {
    mostrarAlerta('erro', 'Erro ao comunicar com o servidor.');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Validar ficheiro';
  }
}

function renderRelatorio(d, tipo) {
  document.getElementById('relatorio').style.display = 'block';
  document.getElementById('rTotal').textContent = d.total_registos || 0;
  document.getElementById('rAvisos').textContent = d.total_avisos || 0;
  document.getElementById('rErros').textContent = d.total_erros || 0;
	
	// Mostrar duplicados se existirem
	const rDupEl = document.getElementById('rDuplicados');
	const dupBloco = document.getElementById('blocoDuplicados');
	if (d.total_duplicados > 0) {
	    rDupEl.textContent = d.total_duplicados;
	    dupBloco.style.display = 'block';
	} else {
	    dupBloco.style.display = 'none';
	}

  const pill = document.getElementById('pillEstado');
  if (d.total_erros > 0) {
    pill.textContent = 'Com erros críticos';
    pill.className = 'pill pill-vermelho';
  } else if (d.total_avisos > 0) {
    pill.textContent = 'Com avisos';
    pill.className = 'pill pill-amarelo';
	} else if (d.total_duplicados > 0 && document.getElementById('modoActualizacao').checked) {
    pill.textContent = 'Com actualizações pendentes';
    pill.className = 'pill pill-amarelo';
	} else {
    pill.textContent = 'Pronto para importar';
    pill.className = 'pill pill-verde';
  }

  // Erros
  const listaErros = document.getElementById('listaErros');
  if (d.erros && d.erros.length > 0) {
    listaErros.style.display = 'flex';
    listaErros.innerHTML = d.erros.map(e =>
      `<li class="msg-erro">✕ ${e}</li>`
    ).join('');
  } else {
    listaErros.style.display = 'none';
  }

  // Avisos
  const listaAvisos = document.getElementById('listaAvisos');
  if (d.avisos && d.avisos.length > 0) {
    listaAvisos.style.display = 'flex';
    const mostrados = d.avisos.length;
    const total = d.total_avisos;
    listaAvisos.innerHTML = d.avisos.map(a =>
      `<li class="msg-aviso">⚠ ${a}</li>`
    ).join('');
    if (total > mostrados) {
      listaAvisos.innerHTML += `<li style="color:var(--texto-sub);padding:0.4rem 0.6rem;font-size:0.75rem">
        … e mais ${total - mostrados} avisos
      </li>`;
    }
  } else {
    listaAvisos.style.display = 'none';
  }

  // Acções
  const acoes = document.getElementById('acoesRelatorio');
  const modoAct = document.getElementById('modoActualizacao').checked;
  const temAlgoParaFazer = d.total_novos > 0 || (modoAct && d.total_duplicados_bd > 0);

  if (d.total_erros === 0 && temAlgoParaFazer) {
    const labelBtn = modoAct && d.total_duplicados_bd > 0
      ? `Actualizar ${d.total_duplicados_bd} registos existentes` + (d.total_novos > 0 ? ` e importar ${d.total_novos} novos` : '')
      : `Importar ${d.total_novos} registos`;
    acoes.innerHTML = `
      <button class="btn btn-confirmar" onclick="confirmarImportacao('${tipo}')">
        ${labelBtn}
      </button>
      <button class="btn btn-cancelar" onclick="cancelar()">Cancelar</button>
    `;
  } else if (d.total_erros > 0) {
    acoes.innerHTML = `
      <button class="btn btn-cancelar" onclick="cancelar()">Corrigir e tentar novamente</button>
    `;
  } else if (d.total_novos === 0 && d.total_duplicados > 0 && !modoAct) {
    acoes.innerHTML = `<p style="color:var(--texto-sub);font-size:0.85rem">Todos os registos já existem na base de dados.</p>`;
  } else {
    acoes.innerHTML = `<p style="color:var(--texto-sub);font-size:0.85rem">Nenhum registo encontrado no ficheiro.</p>`;
  }
}

// ── Importação final ──────────────────────────────────────────────────────────

async function confirmarImportacao(tipo) {
  if (!ficheiroAtual) return;
  const freguesia = document.getElementById('inputFreguesia').value.trim();
  const modoAct = document.getElementById('modoActualizacao').checked;
  const params = new URLSearchParams({ tipo });
  if (freguesia) params.set('freguesia', freguesia);
  if (modoAct)   params.set('modo_actualizacao', 'true');
  const btn = document.querySelector('.btn-confirmar');
  if (btn) { btn.disabled = true; btn.textContent = 'A importar…'; }
  try {
    const form = new FormData();
    form.append('ficheiro', ficheiroAtual);
    const r = await fetch(`/admin/api/confirmar-upload?${params}`, { method: 'POST', body: form });
    const d = await r.json();
    if (d.sucesso) {
      mostrarAlerta('sucesso', `✓ ${d.mensagem}`);
      cancelar();
    } else {
      mostrarAlerta('erro', `Erro: ${d.mensagem || d.erro}`);
    }
  } catch(e) {
    mostrarAlerta('erro', 'Erro ao comunicar com o servidor.');
  }
}

function cancelar() {
  ficheiroAtual = null;
  dadosValidacao = null;
  document.getElementById('inputFicheiro').value = '';
  document.getElementById('nomeFile').style.display = 'none';
  document.getElementById('nomeFile').textContent = '';
  document.getElementById('btnValidar').disabled = true;
  document.getElementById('relatorio').style.display = 'none';
}

// ── Histórico ────────────────────────────────────────────────────────────────

async function carregarHistorico() {
  try {
    const r = await fetch('/admin/api/uploads');
    const uploads = await r.json();
    const tbody = document.getElementById('corpoHistorico');

    if (!uploads.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="vazio">Nenhuma importação realizada ainda.</td></tr>`;
      return;
    }

    tbody.innerHTML = uploads.map(u => {
      const data = new Date(u.data_upload).toLocaleString('pt-PT');
      const tipoLabel = { batismo: 'Batismos', casamento: 'Casamentos', obito: 'Óbitos' }[u.tipo] || u.tipo;
      return `<tr>
        <td>${data}</td>
        <td style="font-family:monospace;font-size:0.8rem;color:var(--texto-sub)">${u.ficheiro}</td>
        <td><span class="tipo-badge tipo-${u.tipo}">${tipoLabel}</span></td>
        <td>${u.registos.toLocaleString('pt-PT')}</td>
        <td style="color:${u.avisos > 0 ? 'var(--amarelo-cl)' : 'var(--texto-sub)'}">
          ${u.avisos}
        </td>
      </tr>`;
    }).join('');
  } catch(e) {}
}

// ── Limpar Base de Dados ─────────────────────────────────────────────────────

async function confirmarReset() {
  const primeira = confirm("Tens a certeza que queres apagar TODOS os registos?\nEsta acção é irreversível.");
  if (!primeira) return;

  const segunda = confirm("Confirmação final: todos os batismos, casamentos e óbitos serão apagados permanentemente.");
  if (!segunda) return;

  try {
    const r = await fetch('/admin/api/reset-db?confirmar=CONFIRMAR', { method: 'DELETE' });
    const d = await r.json();
    if (d.sucesso) {
      mostrarAlerta('sucesso', '✓ ' + d.mensagem);
      carregarHistorico();
    } else {
      mostrarAlerta('erro', d.detail || 'Erro ao limpar a base de dados.');
    }
  } catch(e) {
    mostrarAlerta('erro', 'Erro ao comunicar com o servidor.');
  }
}

// ── Alertas ──────────────────────────────────────────────────────────────────

function mostrarAlerta(tipo, msg) {
  const el = document.getElementById('alerta');
  el.className = `alerta alerta-${tipo}`;
  el.textContent = msg;
  el.style.display = 'block';
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function esconderAlerta() {
  document.getElementById('alerta').style.display = 'none';
}

// ── Footer editável ───────────────────────────────────────────────────────────

function textoParaHtml(texto) {
  if (!texto) return '';
  // Escapa HTML e converte URLs em links
  const escapado = texto
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  return escapado.replace(
    /(https?:\/\/[^\s]+)/g,
    '<a href="$1" target="_blank" rel="noopener">$1</a>'
  );
}

function actualizarPreviewFooter() {
  const val = document.getElementById('footerTextarea').value;
  const n   = val.length;

  // Contador
  const cont = document.getElementById('footerContador');
  cont.textContent = `${n} / ${FOOTER_MAX}`;
  cont.className   = 'footer-contador' + (n > FOOTER_MAX * 0.9 ? (n >= FOOTER_MAX ? ' excedido' : ' perto') : '');

  // Preview
  document.getElementById('footerPreview').innerHTML = textoParaHtml(val);

  // Footer desta página
  const adminFooter = document.getElementById('footerAdminTexto');
  if (adminFooter) adminFooter.innerHTML = textoParaHtml(val);
}

async function carregarFooter() {
  try {
    const r = await fetch('/admin/api/configuracao/footer');
    const d = await r.json();
    const texto = d.footer_texto || FOOTER_DEFAULT;
    document.getElementById('footerTextarea').value = texto;
    actualizarPreviewFooter();
  } catch(e) {
    document.getElementById('footerTextarea').value = FOOTER_DEFAULT;
    actualizarPreviewFooter();
  }
}

async function guardarFooter() {
  const texto = document.getElementById('footerTextarea').value.trim();
  if (!texto) { mostrarAlerta('erro', 'O texto do rodapé não pode estar vazio.'); return; }
  if (texto.length > FOOTER_MAX) { mostrarAlerta('erro', `Texto demasiado longo (máx. ${FOOTER_MAX} caracteres).`); return; }
  try {
    const r = await fetch('/admin/api/configuracao/footer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ valor: texto }),
    });
    const d = await r.json();
    if (d.sucesso) {
      mostrarAlerta('sucesso', '✓ Rodapé guardado com sucesso.');
    } else {
      mostrarAlerta('erro', d.detail || 'Erro ao guardar.');
    }
  } catch(e) {
    mostrarAlerta('erro', 'Erro ao comunicar com o servidor.');
  }
}

function restaurarFooterDefault() {
  if (!confirm('Restaurar o texto predefinido? O texto actual será substituído.')) return;
  document.getElementById('footerTextarea').value = FOOTER_DEFAULT;
  actualizarPreviewFooter();
}

// Auditoria
async function carregarAuditoria() {
  try {
    const r = await fetch('/admin/api/auditoria');
    const d = await r.json();
    renderAuditoria(d);
  } catch(e) {
    document.getElementById('auditoriaConteudo').innerHTML =
      '<div class="painel"><p class="vazio">Erro ao carregar auditoria.</p></div>';
  }
}

function renderAuditoria(d) {
  const cont = document.getElementById('auditoriaConteudo');
  const t = d.totais;

  cont.innerHTML = `
    <!-- Totais -->
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:1rem;margin-bottom:1rem">
      <div class="painel" style="text-align:center;padding:1rem">
        <div style="font-size:1.8rem;font-weight:700;color:#4A5E76">${(t.total_pedidos||0).toLocaleString('pt-PT')}</div>
        <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--texto-sub);margin-top:0.2rem">Pedidos totais</div>
      </div>
      <div class="painel" style="text-align:center;padding:1rem">
        <div style="font-size:1.8rem;font-weight:700;color:#4A5E76">${(t.ips_unicos||0).toLocaleString('pt-PT')}</div>
        <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--texto-sub);margin-top:0.2rem">IPs únicos</div>
      </div>
      <div class="painel" style="text-align:center;padding:1rem">
        <div style="font-size:1.8rem;font-weight:700;color:${t.total_erros > 0 ? '#c44030' : '#2a9a5a'}">${(t.total_erros||0).toLocaleString('pt-PT')}</div>
        <div style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;color:var(--texto-sub);margin-top:0.2rem">Erros / bloqueios</div>
      </div>
    </div>

    <!-- Por IP -->
    <div class="painel" style="margin-bottom:1rem">
      <div style="font-size:0.7rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--texto-sub);margin-bottom:0.8rem">
        Acessos por IP
      </div>
      ${d.por_ip.length === 0 ? '<p class="vazio">Sem dados</p>' : `
      <table class="tabela-historico">
        <thead>
          <tr>
            <th>IP</th>
            <th>Total</th>
            <th>Pesquisas</th>
            <th>Admin</th>
            <th>Primeiro acesso</th>
            <th>Último acesso</th>
          </tr>
        </thead>
        <tbody>
          ${d.por_ip.map(r => `
            <tr>
              <td style="font-family:monospace;font-size:0.8rem">${r.ip}</td>
              <td style="font-weight:600">${r.total.toLocaleString('pt-PT')}</td>
              <td>${r.pesquisas.toLocaleString('pt-PT')}</td>
              <td>${r.admin > 0 ? `<span style="color:#F4794A;font-weight:500">${r.admin}</span>` : '0'}</td>
              <td style="font-size:0.78rem;color:var(--texto-sub)">${r.primeiro_acesso?.substring(0,16).replace('T',' ') || '—'}</td>
              <td style="font-size:0.78rem;color:var(--texto-sub)">${r.ultimo_acesso?.substring(0,16).replace('T',' ') || '—'}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>`}
    </div>

    <!-- Actividade por dia -->
    <div class="painel" style="margin-bottom:1rem">
      <div style="font-size:0.7rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:var(--texto-sub);margin-bottom:0.8rem">
        Actividade diária (últimos 30 dias)
      </div>
      ${d.por_dia.length === 0 ? '<p class="vazio">Sem dados</p>' : `
      <div style="display:flex;flex-direction:column;gap:0.3rem">
        ${d.por_dia.slice(0,30).map(r => {
          const max = Math.max(...d.por_dia.slice(0,30).map(x => x.total));
          const pct = max ? Math.round(r.total / max * 100) : 0;
          return `
          <div style="display:grid;grid-template-columns:90px 1fr 50px 60px;gap:0.5rem;align-items:center;font-size:0.78rem">
            <span style="color:var(--texto-sub)">${r.dia}</span>
            <div style="background:var(--linha);border-radius:2px;height:7px;overflow:hidden">
              <div style="background:#4A5E76;height:100%;width:${pct}%;border-radius:2px"></div>
            </div>
            <span style="font-weight:500">${r.total}</span>
            <span style="color:var(--texto-sub);font-size:0.72rem">${r.ips_unicos} IP${r.ips_unicos !== 1 ? 's' : ''}</span>
          </div>`;
        }).join('')}
      </div>`}
    </div>

    <!-- Eventos suspeitos -->
		${d.suspeitos.length > 0 ? `
		<div class="painel" style="border-color:#c44030;padding:0;overflow:hidden">
		  <div style="display:flex;justify-content:space-between;align-items:center;
		              padding:0.8rem 1rem;border-bottom:1px solid rgba(196,64,48,0.2)">
		    <div style="font-size:0.7rem;font-weight:600;letter-spacing:0.08em;
		                text-transform:uppercase;color:#c44030">
		      ⚠ Eventos suspeitos (403 · 429 · 5xx)
		    </div>
		    <div style="font-size:0.72rem;color:var(--texto-sub)">${d.suspeitos.length} eventos</div>
		  </div>
		  <div style="max-height:320px;overflow-y:auto">
		    <table class="tabela-historico" style="margin:0">
		      <thead>
		        <tr style="position:sticky;top:0;background:var(--bg2);z-index:1">
		          <th>Data</th><th>IP</th><th>Endpoint</th><th>Status</th>
		        </tr>
		      </thead>
		      <tbody>
		        ${d.suspeitos.map(r => `
	            <tr>
	              <td style="font-size:0.75rem;color:var(--texto-sub)">${r.data?.substring(0,16).replace('T',' ')}</td>
	              <td style="font-family:monospace;font-size:0.78rem">${r.ip}</td>
	              <td style="font-size:0.75rem;color:var(--texto-sub)">${r.endpoint}</td>
	              <td><span style="color:${r.status >= 500 ? '#c44030' : r.status === 429 ? '#c49a20' : '#8a5a00'};font-weight:600">${r.status}</span></td>
	            </tr>
	          `).join('')}
	        </tbody>
	      </table>
		  </div>
    </div>` : ''}
  `;
}

// ══════════════════════════════════════════════════════════════════════════════
// Tokens emitidos
// ══════════════════════════════════════════════════════════════════════════════

async function carregarTokens() {
  try {
    const r = await fetch('/admin/api/tokens');
    renderTokens(await r.json());
  } catch(e) {
    document.getElementById('listaTokens').innerHTML =
      '<p class="vazio">Erro ao carregar tokens.</p>';
  }
}

function renderTokens(tokens) {
  const cont = document.getElementById('listaTokens');
  if (!tokens.length) {
    cont.innerHTML = '<p class="vazio">Nenhum token emitido ainda.</p>';
    return;
  }
  cont.innerHTML = tokens.map(t => {
    const revogado = !t.activo;
    return `
    <div class="token-card ${revogado ? 'revogado' : ''}">
      <div>
        <div class="token-nome">${t.nome}</div>
        <div class="token-preview">${t.token_preview}</div>
        ${t.descricao ? `<div style="font-size:0.75rem;color:var(--texto-sub);margin-top:0.2rem">${t.descricao}</div>` : ''}
        <div class="token-meta">
          ${revogado
            ? `<span class="token-chip rev">revogado</span>`
            : `<span class="token-chip ok">activo</span>`}
          <span class="token-chip">criado ${t.data_criacao?.substring(0,10)}</span>
          ${t.ultimo_uso
            ? `<span class="token-chip ok">último uso ${t.ultimo_uso.substring(0,16).replace('T',' ')}</span>`
            : `<span class="token-chip">nunca usado</span>`}
        </div>
      </div>
      <div class="acoes-fed">
        ${!revogado
          ? `<button class="btn btn-rev" onclick="revogarToken(${t.id})">Revogar</button>`
          : ''}
        <button class="btn btn-del" onclick="removerToken(${t.id})">Remover</button>
      </div>
    </div>`;
  }).join('');
}

async function criarToken() {
  const nome = document.getElementById('tokenNome').value.trim();
  const desc = document.getElementById('tokenDesc').value.trim();
  const status = document.getElementById('tokenStatus');
  const btn    = document.getElementById('btnCriarToken');

  if (!nome) {
    status.textContent = '⚠ O nome é obrigatório.';
    status.style.color = 'var(--vermelho-cl)';
    return;
  }

  btn.disabled = true; btn.textContent = 'A gerar…';
  status.textContent = ''; 

  try {
    const r = await fetch('/admin/api/tokens', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome, descricao: desc || null }),
    });
    const d = await r.json();
    if (!r.ok) {
      status.textContent = `✕ ${d.detail}`;
      status.style.color = 'var(--vermelho-cl)';
    } else {
      // Mostrar token em destaque — único momento em que é visível
      document.getElementById('tokenValor').textContent = d.token;
      document.getElementById('tokenReveal').classList.add('visivel');
      document.getElementById('tokenNome').value = '';
      document.getElementById('tokenDesc').value = '';
      status.textContent = '';
      await carregarTokens();
    }
  } catch(e) {
    status.textContent = '✕ Erro ao comunicar com o servidor.';
    status.style.color = 'var(--vermelho-cl)';
  } finally {
    btn.disabled = false; btn.textContent = 'Gerar token';
  }
}

function copiarToken() {
  const val = document.getElementById('tokenValor').textContent;
  navigator.clipboard.writeText(val).then(() => {
    const btn = document.querySelector('#tokenReveal .btn-primario');
    btn.textContent = '✓ Copiado';
    setTimeout(() => { btn.textContent = 'Copiar'; }, 2000);
  });
}

function fecharTokenReveal() {
  document.getElementById('tokenReveal').classList.remove('visivel');
  document.getElementById('tokenValor').textContent = '';
}

async function revogarToken(id) {
  if (!confirm('Revogar este token?\nO nó que o usa deixará imediatamente de conseguir ligar-se.')) return;
  await fetch(`/admin/api/tokens/${id}/revogar`, { method: 'DELETE' });
  await carregarTokens();
}

async function removerToken(id) {
  if (!confirm('Remover este token permanentemente?')) return;
  await fetch(`/admin/api/tokens/${id}`, { method: 'DELETE' });
  await carregarTokens();
}


// ══════════════════════════════════════════════════════════════════════════════
// Nós federados
// ══════════════════════════════════════════════════════════════════════════════

async function carregarNos() {
  try {
    const r = await fetch('/admin/api/nos-federados');
    renderNos(await r.json());
  } catch(e) {
    document.getElementById('listaNos').innerHTML =
      '<p class="vazio">Erro ao carregar nós.</p>';
  }
}

function renderNos(nos) {
  const cont = document.getElementById('listaNos');
  if (!nos.length) {
    cont.innerHTML = '<p class="vazio">Nenhum nó federado registado ainda.</p>';
    return;
  }
  cont.innerHTML = nos.map(no => {
    const temErro  = !!no.ultimo_erro;
    const inactivo = !no.activo;
    const cls = inactivo ? 'inactivo' : (temErro ? 'com-erro' : '');

    const chipEstado = inactivo
      ? `<span class="no-chip">suspenso</span>`
      : temErro
        ? `<span class="no-chip erro" title="${no.ultimo_erro}">⚠ erro</span>`
        : no.ultimo_ok
          ? `<span class="no-chip ok">✓ ok · ${no.ultimo_ok.substring(0,16).replace('T',' ')}</span>`
          : `<span class="no-chip">não testado</span>`;

    return `
    <div class="no-card ${cls}" id="no-${no.id}">
      <div>
        <div class="no-nome">${no.nome}</div>
        <div class="no-url">${no.url}</div>
        ${no.descricao ? `<div style="font-size:0.75rem;color:var(--texto-sub);margin-top:0.2rem">${no.descricao}</div>` : ''}
        <div class="no-meta">
          ${no.regiao ? `<span class="no-chip regiao">📍 ${no.regiao}</span>` : ''}
          ${chipEstado}
          <span class="no-chip">adicionado ${no.data_adicao?.substring(0,10)}</span>
        </div>
      </div>
      <div class="acoes-fed">
        <button class="btn btn-tst" onclick="testarNo(${no.id})">Testar</button>
        ${no.activo
          ? `<button class="btn btn-rev" onclick="toggleNo(${no.id}, 0)">Suspender</button>`
          : `<button class="btn btn-act" onclick="toggleNo(${no.id}, 1)">Activar</button>`}
        <button class="btn btn-del"
                onclick="removerNo(${no.id}, '${no.nome.replace(/'/g,"\\'")}')">Remover</button>
      </div>
    </div>`;
  }).join('');
}

async function adicionarNo() {
  const url    = document.getElementById('noUrl').value.trim();
  const nome   = document.getElementById('noNome').value.trim();
  const token  = document.getElementById('noToken').value.trim();
  const regiao = document.getElementById('noRegiao').value.trim();
  const desc   = document.getElementById('noDescricao').value.trim();
  const status = document.getElementById('noStatus');
  const btn    = document.getElementById('btnAdicionarNo');

  if (!url || !nome || !token) {
    status.textContent = '⚠ URL, Nome e Token são obrigatórios.';
    status.style.color = 'var(--vermelho-cl)';
    return;
  }

  // Validar formato UUID v4 no cliente
  const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  if (!uuidRe.test(token)) {
    status.textContent = '⚠ O token não parece um UUID v4 válido.';
    status.style.color = 'var(--vermelho-cl)';
    return;
  }

  btn.disabled = true; btn.textContent = 'A verificar…';
  status.textContent = 'A contactar o nó remoto…';
  status.style.color = 'var(--texto-sub)';

  try {
    const r = await fetch('/admin/api/nos-federados', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url, nome, token,
        regiao: regiao || null,
        descricao: desc || null,
      }),
    });
    const d = await r.json();
    if (!r.ok) {
      status.textContent = `✕ ${d.detail}`;
      status.style.color = 'var(--vermelho-cl)';
    } else {
      status.textContent = `✓ Nó adicionado com sucesso.`;
      status.style.color = 'var(--verde-clr)';
      ['noUrl','noNome','noToken','noRegiao','noDescricao'].forEach(
        id => document.getElementById(id).value = ''
      );
      await carregarNos();
      setTimeout(() => { status.textContent = ''; }, 4000);
    }
  } catch(e) {
    status.textContent = '✕ Erro ao comunicar com o servidor.';
    status.style.color = 'var(--vermelho-cl)';
  } finally {
    btn.disabled = false; btn.textContent = 'Verificar e adicionar';
  }
}

async function testarNo(id) {
  const card = document.getElementById(`no-${id}`);
  const btn  = card?.querySelector('.btn-tst');
  if (btn) { btn.disabled = true; btn.textContent = 'A testar…'; }
  try {
    const r = await fetch(`/admin/api/nos-federados/${id}/testar`, { method: 'POST' });
    const d = await r.json();
    if (d.sucesso) {
      const s = d.info?.stats;
      const resumo = s
        ? `B:${s.batismos?.total||0} · C:${s.casamentos?.total||0} · Ó:${s.obitos?.total||0}`
        : '';
      mostrarAlerta('sucesso', `✓ Nó acessível. ${resumo}`);
    } else {
      mostrarAlerta('erro', `✕ Nó inacessível: ${d.erro}`);
    }
  } catch(e) {
    mostrarAlerta('erro', 'Erro ao testar o nó.');
  }
  await carregarNos();
}

async function toggleNo(id, activo) {
  await fetch(`/admin/api/nos-federados/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ activo }),
  });
  await carregarNos();
}

async function removerNo(id, nome) {
  if (!confirm(`Remover o nó "${nome}"?\nEsta acção não pode ser desfeita.`)) return;
  await fetch(`/admin/api/nos-federados/${id}`, { method: 'DELETE' });
  await carregarNos();
  mostrarAlerta('sucesso', `✓ Nó "${nome}" removido.`);
}

carregarFreguesias();
carregarAuditoria();
carregarFooter();
carregarTokens();
carregarNos();
