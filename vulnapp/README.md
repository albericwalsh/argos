# Vulnerable Test App (pour tester le module Nikto)

⚠️ À utiliser UNIQUEMENT en local, sur un réseau isolé. Ne jamais exposer sur Internet.

## Lancer avec Docker

```bash
cd vulnapp
docker build -t vulnapp .
docker run --rm -p 4000:4000 vulnapp
```

L'app est accessible sur http://localhost:4000 (ou http://<ton-ip-locale>:4000)

## Lancer sans Docker

```bash
cd vulnapp
npm install
node server.js
```

## Tester avec le module Nikto

Dans ton workflow Argos, configure :
- `target` : `host.docker.internal` (si Nikto tourne dans Docker et l'app aussi via `-p 3000:3000`)
  ou l'IP locale de ta machine (ex: `10.105.1.69`)
- `port` : `3000`

## Endpoints volontairement vulnérables

- `/admin` + `/admin/login` — login avec creds par défaut admin/admin
- `/.env` — variables d'environnement exposées (DB creds, API key)
- `/backup.sql` — dump SQL exposé
- `/.git/config` — repo git exposé
- `/phpinfo.php` — disclosure infos PHP/Apache (fictif)
- `/server-status` — fausse page Apache status
- `/wp-config.php.bak` — backup WordPress config
- `/robots.txt` — révèle des chemins sensibles
- Headers de sécurité manquants (X-Frame-Options, CSP, X-Content-Type-Options)
- `X-Powered-By: Express` exposé
- Cookie de session sans `Secure`/`HttpOnly`
- Méthodes PUT/DELETE acceptées sur `/upload`

Nikto devrait remonter une dizaine de findings de sévérités variées (low/medium/high).
