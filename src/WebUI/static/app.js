const modules = {
  nmap: { title: 'Nmap', desc: 'Scanner de ports basique (simulation).', options: [
    { name: 'ports', label: 'Ports', type: 'text', placeholder: '1-1024,80,443' },
    { name: 'fast', label: 'Fast scan (-F)', type: 'checkbox' }
  ] },
  ffuf: { title: 'FFUF', desc: 'Fuzzer de répertoires/paramètres (simulation).', options: [
    { name: 'threads', label: 'Threads', type: 'number', placeholder: '40', min:1 },
    { name: 'extensions', label: 'Extensions (csv)', type: 'text', placeholder: 'php,html,txt' }
  ] },
  workflows: { title: 'Workflows', desc: 'Exécutions prédéfinies.', options: [
    { name: 'workflow', label: 'Workflow', type: 'text', placeholder: 'quick ou enum' }
  ] }
};

const workflows = {
  quick: { title: 'Quick scan', steps: ['nmap -T4 -F', 'report'] },
  enum: { title: 'Enumeration', steps: ['nmap -sV', 'ffuf -u /FUZZ -w wordlist.txt'] }
};

document.addEventListener('DOMContentLoaded', ()=>{
  const navItems = document.querySelectorAll('.sidebar nav li');
  const title = document.getElementById('title');
  const card = document.getElementById('card-desc');
  const output = document.getElementById('output');
  const target = document.getElementById('target');
  const runBtn = document.getElementById('run');
  const app = document.querySelector('.app');
  let _startTimerA = null;
  let _startTimerB = null;

  // centralized start sequence: animate and then activate moduleKey (or null)
  function startSequence(moduleKey){
    // clear any pending timers
    if(_startTimerA) clearTimeout(_startTimerA);
    if(_startTimerB) clearTimeout(_startTimerB);
    const hero = document.getElementById('hero');
    if(app) app.classList.add('transitioning');
    _startTimerA = setTimeout(()=>{
      if(app) app.classList.add('started');
      if(moduleKey){ activateModuleByKey(moduleKey); }
      const tgt = document.getElementById('target'); if(tgt) tgt.focus();
    }, 30);
    _startTimerB = setTimeout(()=>{
      if(app) app.classList.add('hero-hidden');
      try{ window.scrollTo({ top: 0, behavior: 'auto' }); }catch(e){ document.documentElement.scrollTop = 0; }
      if(app) app.classList.remove('transitioning');
    }, 600);
  }

  function activateModuleByKey(key){
    // set active state in nav
    navItems.forEach(n=>n.classList.remove('active'));
    const nav = Array.from(navItems).find(n=>n.dataset.module===key);
    if(nav) nav.classList.add('active');
    if(modules[key]){
      title.textContent = modules[key].title;
      card.textContent = modules[key].desc;
      output.textContent = `Module: ${modules[key].title}\n${modules[key].desc}\n\nPrêt.`;
      renderConfigFor(key);
    }
  }

  function transitionToModule(key){
    const wrapper = document.querySelector('.modules-wrapper');
    if(!wrapper || !app || !app.classList.contains('started')) return;

    // Inline styles override all CSS cascade (specificity 1-0-0) — guaranteed to work
    wrapper.style.transition = 'opacity 0.25s ease, transform 0.25s ease';
    wrapper.style.opacity = '0';
    wrapper.style.transform = 'translate3d(0,8px,0)';

    setTimeout(()=>{
      activateModuleByKey(key);

      // Lock at 0 without transition so fade-in starts cleanly from 0
      wrapper.style.transition = 'none';
      void wrapper.offsetHeight; // force reflow
      wrapper.style.transition = 'opacity 0.3s ease 0.04s, transform 0.3s ease 0.04s';
      wrapper.style.opacity = '1';
      wrapper.style.transform = 'translate3d(0,0,0)';

      try{ window.scrollTo({ top: 0, behavior: 'auto' }); }catch(e){ document.documentElement.scrollTop = 0; }

      // Remove inline styles after fade-in so CSS stays in control
      setTimeout(()=>{
        wrapper.style.transition = '';
        wrapper.style.opacity = '';
        wrapper.style.transform = '';
      }, 380);
    }, 260);
  }

  function clearWrapperInlineStyles(){
    const wrapper = document.querySelector('.modules-wrapper');
    if(wrapper){ wrapper.style.transition = ''; wrapper.style.opacity = ''; wrapper.style.transform = ''; }
  }

  navItems.forEach(it=>it.addEventListener('click', ()=>{
    const key = it.dataset.module;
    if(!key) return;

    // Home handling: hide modules and show hero
    if(key === 'home'){
      navItems.forEach(n=>n.classList.remove('active'));
      it.classList.add('active');
      // cancel pending start timers
      if(_startTimerA) { clearTimeout(_startTimerA); _startTimerA = null; }
      if(_startTimerB) { clearTimeout(_startTimerB); _startTimerB = null; }
      // clean up any lingering inline styles so CSS entrance animation works on re-entry
      clearWrapperInlineStyles();
      // show hero again and play reverse animation smoothly
      if(app){
        app.classList.remove('hero-hidden');
        setTimeout(()=>{
          app.classList.remove('started');
          setTimeout(()=>{ const hero = document.getElementById('hero'); if(hero) hero.scrollIntoView({behavior:'smooth'}); }, 620);
        }, 30);
      }
      return;
    }

    // Module click: decide whether to do full start or just transition
    // Show active state immediately for feedback
    navItems.forEach(n=>n.classList.remove('active'));
    it.classList.add('active');

    if(app && app.classList.contains('started')){
      // UI already open, just transition to this module
      transitionToModule(key);
    } else {
      // UI not open yet, do full open sequence with this module
      startSequence(key);
    }
  }));

  // start button scrolls to main content
  const startBtn = document.getElementById('start-btn');
  if(startBtn){
    startBtn.addEventListener('click', ()=>{
      const hero = document.getElementById('hero');
      // prepare transition state
      if(app) app.classList.add('transitioning');
      // trigger animations shortly after to allow CSS transitions
      setTimeout(()=>{
        if(app) app.classList.add('started');
        // activate first module directly — do NOT call .click() here since started is already
        // true and click() would trigger transitionToModule instead of the CSS entrance animation
        const firstModule = Array.from(navItems).find(n=>n.dataset.module && n.dataset.module!=='home');
        if(firstModule){
          navItems.forEach(n=>n.classList.remove('active'));
          firstModule.classList.add('active');
          activateModuleByKey(firstModule.dataset.module);
        }
        const tgt = document.getElementById('target'); if(tgt) tgt.focus();
      }, 30);

      // hide hero after animation completes to give 'page' effect (use class to avoid layout jumps)
      setTimeout(()=>{
        if(app) app.classList.add('hero-hidden');
        // ensure modules content is positioned at very top immediately
        try{ window.scrollTo({ top: 0, behavior: 'auto' }); }catch(e){ document.documentElement.scrollTop = 0; }
        if(app) app.classList.remove('transitioning');
      }, 600);
    });
  }

  runBtn.addEventListener('click', ()=>{
    const active = document.querySelector('.sidebar nav li.active');
    const key = active?.dataset.module || 'nmap';
    const tgt = target.value.trim() || '<no target specified>';
    appendOutput(`> Lancement de ${modules[key].title} sur ${tgt} ...`);
    simulateRun(key, tgt);
  });

  // duplicate run button in panel
  const run2 = document.getElementById('run2');
  if(run2){
    run2.addEventListener('click', ()=>{
      const active = document.querySelector('.sidebar nav li.active');
      const key = active?.dataset.module || 'nmap';
      const tgt = target.value.trim() || '<no target specified>';
      const payload = collectConfig(key, tgt);
      appendOutput(`> POST /api/run ${JSON.stringify(payload)}`);
      callRunApi(payload).then(r=>appendOutput('[api] ' + r)).catch(e=>appendOutput('[api error] ' + e));
    });
  }

  // file input
  const wordlistInput = document.getElementById('wordlist');
  const wordlistName = document.getElementById('wordlist-name');
  if(wordlistInput){
    wordlistInput.addEventListener('change', ()=>{
      const f = wordlistInput.files[0];
      wordlistName.textContent = f ? f.name : 'Aucune sélection';
    });
  }

  // workflows
  const wfList = document.getElementById('workflows-list');
  if(wfList){
    wfList.addEventListener('click', (ev)=>{
      const li = ev.target.closest('li');
      if(!li) return;
      const key = li.dataset.workflow;
      const wf = workflows[key];
      appendOutput(`> Workflow: ${wf.title}\nsteps: ${wf.steps.join(' && ')}`);
    });
  }

  function appendOutput(text){
    output.textContent += '\n' + text;
    output.scrollTop = output.scrollHeight;
  }

  function simulateRun(key, tgt){
    appendOutput('[simulation] initialisation...');
    setTimeout(()=> appendOutput(`[simulation] ${modules[key].title} en cours sur ${tgt} (résultats simulés)...`), 800);
    setTimeout(()=> appendOutput('[simulation] 22/tcp open\n[simulation] 80/tcp open\n[simulation] opération terminée.'), 1600);
  }

  function renderConfigFor(key){
    const cfg = document.getElementById('config-fields');
    if(!cfg){ return; }
    cfg.innerHTML = '';
    const mod = modules[key];
    if(!mod || !mod.options){ cfg.textContent = 'Aucune option pour ce module.'; return; }
    mod.options.forEach(opt=>{
      const row = document.createElement('div'); row.className='form-row';
      const label = document.createElement('label'); label.textContent = opt.label; row.appendChild(label);
      let input;
      if(opt.type==='checkbox'){
        input = document.createElement('input'); input.type='checkbox'; input.name=opt.name;
      } else {
        input = document.createElement('input'); input.type=opt.type||'text'; input.name=opt.name; input.placeholder = opt.placeholder||'';
        if(opt.min) input.min = opt.min;
      }
      row.appendChild(input);
      cfg.appendChild(row);
    });
  }

  function collectConfig(key, tgt){
    const payload = { module:key, target:tgt, options:{} };
    const form = document.getElementById('config-form');
    if(form){
      const inputs = form.querySelectorAll('input');
      inputs.forEach(i=>{
        if(i.type==='file') return;
        if(i.type==='checkbox') payload.options[i.name]=i.checked;
        else payload.options[i.name]=i.value;
      });
    }
    const f = document.getElementById('wordlist')?.files[0];
    if(f) payload.wordlist = f.name;
    return payload;
  }

  async function callRunApi(payload){
    try{
      const res = await fetch('/api/run', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload) });
      if(!res.ok) throw new Error('non-ok status '+res.status);
      const txt = await res.text();
      return txt || 'ok';
    }catch(err){
      // backend absent: simulate response
      await new Promise(r=>setTimeout(r,700));
      return '[simulation] backend absent — résultat simulé';
    }
  }
});
