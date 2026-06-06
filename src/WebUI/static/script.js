/* ── NAVIGATION ─────────────────────────────────── */
  function showPage(id, el, breadcrumb) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const page = document.getElementById('page-' + id);
    page.classList.add('active');
    page.classList.remove('fade-in');
    void page.offsetWidth;
    page.classList.add('fade-in');
    if (el) el.classList.add('active');
    document.getElementById('breadcrumb').innerHTML = '/ <span>' + breadcrumb + '</span>';
  }

  /* ── QUICK RUN ──────────────────────────────────── */
  const wfData = {
    'recon-full': {
      steps: [
        { n: 1, label: 'nslookup — résolution DNS du domaine' },
        { n: 2, label: 'whois — récupération infos registrar' },
        { n: 3, label: 'subfinder — énumération sous-domaines' },
        { n: 4, label: 'httpx_probe — sondage des hôtes actifs' },
        { n: 5, label: 'report_gen — génération du rapport PDF' },
      ]
    },
    'port-scan': {
      steps: [
        { n: 1, label: 'nmap_scan — scan TCP/UDP du réseau' },
        { n: 2, label: 'report_gen — export des résultats CSV' },
      ]
    },
    'dns-enum': {
      steps: [
        { n: 1, label: 'nslookup — résolution des enregistrements' },
        { n: 2, label: 'subfinder — force brute sous-domaines' },
      ]
    },
    'vuln-check': {
      steps: [
        { n: 1, label: 'httpx_probe — détection des services web' },
        { n: 2, label: 'screenshot — capture des interfaces' },
        { n: 3, label: 'report_gen — rapport de vulnérabilités' },
      ]
    }
  };

  function updateWorkflowSummary() {
    const sel = document.getElementById('wf-select').value;
    const inputs = document.getElementById('wf-inputs');
    const placeholder = document.getElementById('wf-placeholder');
    if (!sel) { inputs.style.display = 'none'; placeholder.style.display = 'block'; return; }
    inputs.style.display = 'block';
    placeholder.style.display = 'none';
    const steps = wfData[sel]?.steps || [];
    document.getElementById('wf-steps').innerHTML = steps.map(s =>
      `<div class="workflow-step"><div class="step-num">${s.n}</div>${s.label}</div>`
    ).join('');
  }

  function launchWorkflow() {
    const sel = document.getElementById('wf-select').value;
    const dom = document.getElementById('input-domaine').value.trim();
    if (!dom) { document.getElementById('input-domaine').focus(); return; }
    alert(`🚀 Lancement de "${sel}" sur "${dom}"`);
  }

  /* ── CANVAS: ADD STEP ───────────────────────────── */
  let stepCount = 0;
  function addStep() {
    stepCount++;
    const flow = document.getElementById('canvas-flow');
    const end = flow.querySelector('.wf-end-node');
    const conn1 = document.createElement('div'); conn1.className = 'wf-connector';
    const node = document.createElement('div');
    node.className = 'wf-add-step';
    node.style.cssText = 'border-style:solid;border-color:var(--border2);cursor:default;text-align:left;padding:12px 16px;width:220px';
    node.innerHTML = `<div style="font-family:var(--font-mono);font-size:10px;color:var(--muted);margin-bottom:4px">ÉTAPE ${stepCount}</div><div style="font-size:12px;font-weight:600">— module non défini —</div>`;
    const conn2 = document.createElement('div'); conn2.className = 'wf-connector';
    flow.insertBefore(conn1, end);
    flow.insertBefore(node, end);
    flow.insertBefore(conn2, end);
    document.getElementById('canvas-empty').style.display = 'none';
  }