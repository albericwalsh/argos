/**
 * static/decrypt.js
 * ──────────────────
 * Chiffrement/déchiffrement AES-256-GCM côté client pour le WebUI Argos.
 *
 * PRINCIPE DE SÉCURITÉ :
 *   - Le serveur Python (WebUI et API) ne manipule JAMAIS de texte en clair
 *     pour les missions / rapports / workflows.
 *   - La clé (enc_key) est lue depuis <meta name="argos-enc-key"> injectée
 *     par base.html, gardée en mémoire JS, jamais en localStorage.
 *   - Lecture ET écriture passent par /proxy/files/... (cookie HttpOnly
 *     transmis automatiquement par le navigateur).
 *
 * API publique :
 *   Lecture :
 *     ArgosDecrypt.listMissions()                       → { name: [files] }
 *     ArgosDecrypt.listMissionFiles(name)                → [files]
 *     ArgosDecrypt.listReports()                         → [files]
 *     ArgosDecrypt.listWorkflows()                       → [files]
 *     ArgosDecrypt.fetchMission(name, filename)          → Blob
 *     ArgosDecrypt.fetchReport(filename)                 → Blob
 *     ArgosDecrypt.fetchWorkflow(filename)                → Blob
 *     ArgosDecrypt.fetchMissionJSON(name, filename)       → Object (parsed)
 *     ArgosDecrypt.fetchWorkflowJSON(filename)            → Object (parsed)
 *
 *   Écriture (chiffre en JS, envoie déjà chiffré) :
 *     ArgosDecrypt.saveWorkflow(filename, jsObject)        → Response JSON
 *     ArgosDecrypt.saveMissionFile(name, filename, jsObject) → Response JSON
 *     ArgosDecrypt.saveReport(filename, jsObject)          → Response JSON
 *
 *   Affichage :
 *     ArgosDecrypt.displayPdf(blob, iframeEl)
 *     ArgosDecrypt.displayHtml(blob, iframeEl)
 *     ArgosDecrypt.download(blob, filename)
 */

const ArgosDecrypt = (() => {

  // ── Clé chargée depuis le meta tag (une seule fois) ──────────────────────
  let _cachedKey = null;

  function _getEncKey() {
    if (_cachedKey) return _cachedKey;
    const meta = document.querySelector('meta[name="argos-enc-key"]');
    if (!meta || !meta.content) {
      console.error('[ArgosDecrypt] enc_key introuvable dans le meta tag');
      return null;
    }
    _cachedKey = meta.content;
    meta.remove();   // défense en profondeur : retire du DOM après lecture
    return _cachedKey;
  }


  // ── Web Crypto : clé ──────────────────────────────────────────────────────

  async function _importDecryptKey(b64Key) {
    const raw = _b64ToBytes(b64Key);
    return crypto.subtle.importKey('raw', raw, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
  }

  async function _importEncryptKey(b64Key) {
    const raw = _b64ToBytes(b64Key);
    return crypto.subtle.importKey('raw', raw, { name: 'AES-GCM', length: 256 }, false, ['encrypt']);
  }


  // ── Déchiffrement ─────────────────────────────────────────────────────────

  async function _decrypt(payload) {
    const b64Key = _getEncKey();
    if (!b64Key) throw new Error('Clé de chiffrement indisponible');

    const key        = await _importDecryptKey(b64Key);
    const nonce      = _b64ToBytes(payload.nonce);
    const ciphertext = _b64ToBytes(payload.ciphertext);

    const plaintext = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: nonce }, key, ciphertext);
    const mime = _detectMime(payload.original_name || '');
    return new Blob([plaintext], { type: mime });
  }

  async function _decryptToObject(payload) {
    const blob = await _decrypt(payload);
    const text = await blob.text();
    return JSON.parse(text);
  }


  // ── Chiffrement ───────────────────────────────────────────────────────────

  /**
   * Chiffre un objet JS (sera sérialisé en JSON) ou une chaîne brute.
   * Retourne { nonce, ciphertext, original_name } prêt à envoyer en PUT.
   */
  async function _encrypt(data, originalName) {
    const b64Key = _getEncKey();
    if (!b64Key) throw new Error('Clé de chiffrement indisponible');

    const key   = await _importEncryptKey(b64Key);
    const nonce = crypto.getRandomValues(new Uint8Array(12));

    const plaintext = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
    const encoded   = new TextEncoder().encode(plaintext);

    const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce }, key, encoded);

    return {
      nonce:         _bytesToBase64Url(nonce),
      ciphertext:    _bytesToBase64Url(new Uint8Array(ciphertext)),
      original_name: originalName,
    };
  }


  // ── Fetch / Put via proxy ────────────────────────────────────────────────

  async function _proxyGet(path) {
    const res = await fetch(path, { credentials: 'same-origin' });
    if (res.status === 401) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      throw new Error('Session expirée');
    }
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async function _proxyPut(path, payload) {
    const res = await fetch(path, {
      method:      'PUT',
      credentials: 'same-origin',
      headers:     { 'Content-Type': 'application/json' },
      body:        JSON.stringify(payload),
    });
    if (res.status === 401) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
      throw new Error('Session expirée');
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }


  // ── Listing (lecture des métadonnées, pas de contenu) ──────────────────────

  async function listMissions()              { return _proxyGet('/proxy/files/missions'); }
  async function listMissionFiles(name)       { return _proxyGet(`/proxy/files/missions/${encodeURIComponent(name)}`); }
  async function listReports()                { return _proxyGet('/proxy/files/reports'); }
  async function listWorkflows()              { return _proxyGet('/proxy/files/workflows'); }


  // ── Lecture déchiffrée ────────────────────────────────────────────────────

  async function fetchMission(missionName, filename) {
    const payload = await _proxyGet(`/proxy/files/missions/${encodeURIComponent(missionName)}/${encodeURIComponent(filename)}`);
    return _decrypt(payload);
  }

  async function fetchReport(filename) {
    const payload = await _proxyGet(`/proxy/files/reports/${encodeURIComponent(filename)}`);
    return _decrypt(payload);
  }

  async function fetchWorkflow(filename) {
    const payload = await _proxyGet(`/proxy/files/workflows/${encodeURIComponent(filename)}`);
    return _decrypt(payload);
  }

  /** Raccourci : récupère et parse directement un JSON de mission. */
  async function fetchMissionJSON(missionName, filename) {
    const payload = await _proxyGet(`/proxy/files/missions/${encodeURIComponent(missionName)}/${encodeURIComponent(filename)}`);
    return _decryptToObject(payload);
  }

  /** Raccourci : récupère et parse directement un JSON de workflow. */
  async function fetchWorkflowJSON(filename) {
    const payload = await _proxyGet(`/proxy/files/workflows/${encodeURIComponent(filename)}`);
    return _decryptToObject(payload);
  }


  // ── Écriture chiffrée ─────────────────────────────────────────────────────

  /**
   * Chiffre un objet workflow en JS puis l'envoie déjà chiffré à l'API.
   * Le serveur (WebUI et API) ne voit jamais le clair.
   */
  async function saveWorkflow(filename, jsObject) {
    const safeName = filename.endsWith('.json') ? filename : `${filename}.json`;
    const payload  = await _encrypt(jsObject, safeName);
    return _proxyPut(`/proxy/files/workflows/${encodeURIComponent(safeName)}`, payload);
  }

  async function saveMissionFile(missionName, filename, jsObject) {
    const safeName = filename.endsWith('.json') ? filename : `${filename}.json`;
    const payload  = await _encrypt(jsObject, safeName);
    return _proxyPut(`/proxy/files/missions/${encodeURIComponent(missionName)}/${encodeURIComponent(safeName)}`, payload);
  }

  async function saveReport(filename, jsObjectOrBytes) {
    const payload = await _encrypt(jsObjectOrBytes, filename);
    return _proxyPut(`/proxy/files/reports/${encodeURIComponent(filename)}`, payload);
  }


  // ── Helpers d'affichage ───────────────────────────────────────────────────

  function displayPdf(blob, iframeEl) {
    const url = URL.createObjectURL(blob);
    iframeEl.src = url;
    iframeEl.onload = () => URL.revokeObjectURL(url);
  }

  function displayHtml(blob, iframeEl) {
    blob.text().then(html => { iframeEl.srcdoc = html; });
  }

  function download(blob, filename) {
    const a    = document.createElement('a');
    a.href     = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }


  // ── Utils ─────────────────────────────────────────────────────────────────

  function _b64ToBytes(b64) {
    const std = b64.replace(/-/g, '+').replace(/_/g, '/');
    const bin = atob(std);
    return Uint8Array.from(bin, c => c.charCodeAt(0));
  }

  function _bytesToBase64Url(bytes) {
    const bin = Array.from(bytes, b => String.fromCharCode(b)).join('');
    return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function _detectMime(name) {
    const n = name.replace(/\.enc$/, '').toLowerCase();
    if (n.endsWith('.pdf'))  return 'application/pdf';
    if (n.endsWith('.html')) return 'text/html';
    if (n.endsWith('.json')) return 'application/json';
    return 'application/octet-stream';
  }


  // ── Export ────────────────────────────────────────────────────────────────
  return {
    listMissions, listMissionFiles, listReports, listWorkflows,
    fetchMission, fetchReport, fetchWorkflow,
    fetchMissionJSON, fetchWorkflowJSON,
    saveWorkflow, saveMissionFile, saveReport,
    displayPdf, displayHtml, download,
  };

})();

window.ArgosDecrypt = ArgosDecrypt;