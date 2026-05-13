const modules = {
  nmap: { title: 'Nmap', desc: 'Scanner de ports basique (simulation).' },
  ffuf: { title: 'FFUF', desc: 'Fuzzer de répertoires/paramètres (simulation).' },
  workflows: { title: 'Workflows', desc: 'Exécutions prédéfinies.' }
};

document.addEventListener('DOMContentLoaded', ()=>{
  const navItems = document.querySelectorAll('.sidebar nav li');
  const title = document.getElementById('title');
  const card = document.getElementById('card-desc');
  const output = document.getElementById('output');
  const target = document.getElementById('target');
  const runBtn = document.getElementById('run');

  navItems.forEach(it=>it.addEventListener('click', ()=>{
    navItems.forEach(n=>n.classList.remove('active'));
    it.classList.add('active');
    const key = it.dataset.module;
    title.textContent = modules[key].title;
    card.textContent = modules[key].desc;
    output.textContent = `Module: ${modules[key].title}\n${modules[key].desc}\n\nPrêt.`;
  }));

  runBtn.addEventListener('click', ()=>{
    const active = document.querySelector('.sidebar nav li.active');
    const key = active?.dataset.module || 'nmap';
    const tgt = target.value.trim() || '<no target specified>';
    appendOutput(`> Lancement de ${modules[key].title} sur ${tgt} ...`);
    simulateRun(key, tgt);
  });

  function appendOutput(text){
    output.textContent += '\n' + text;
    output.scrollTop = output.scrollHeight;
  }

  function simulateRun(key, tgt){
    appendOutput('[simulation] initialisation...');
    setTimeout(()=> appendOutput(`[simulation] ${modules[key].title} en cours sur ${tgt} (résultats simulés)...`), 800);
    setTimeout(()=> appendOutput('[simulation] 22/tcp open\n[simulation] 80/tcp open\n[simulation] opération terminée.'), 1600);
  }
});
