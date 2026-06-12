const express = require("express");
const app = express();

// --- Pas de helmet, pas de désactivation de X-Powered-By ---
// (Nikto va voir "X-Powered-By: Express")

// --- Page d'accueil ---
app.get("/", (req, res) => {
  res.send(`
    <html>
      <head><title>Vulnerable Test App</title></head>
      <body>
        <h1>Vulnerable Test App</h1>
        <p>Cette appli sert UNIQUEMENT à tester ton module Nikto en local.</p>
        <ul>
          <li><a href="/admin">/admin</a></li>
          <li><a href="/phpinfo.php">/phpinfo.php</a></li>
          <li><a href="/.env">/.env</a></li>
          <li><a href="/backup.sql">/backup.sql</a></li>
          <li><a href="/.git/config">/.git/config</a></li>
          <li><a href="/server-status">/server-status</a></li>
          <li><a href="/robots.txt">/robots.txt</a></li>
        </ul>
      </body>
    </html>
  `);
});

// --- robots.txt qui révèle des chemins sensibles ---
app.get("/robots.txt", (req, res) => {
  res.type("text/plain").send(
    "User-agent: *\nDisallow: /admin\nDisallow: /backup\nDisallow: /private\n"
  );
});

// --- Page admin "login" non protégée ---
app.get("/admin", (req, res) => {
  res.send(`
    <html><body>
      <h2>Admin Panel</h2>
      <form method="post" action="/admin/login">
        <input name="user" placeholder="user (default: admin)">
        <input name="pass" type="password" placeholder="pass (default: admin)">
        <button>Login</button>
      </form>
    </body></html>
  `);
});

app.post("/admin/login", express.urlencoded({ extended: true }), (req, res) => {
  if (req.body.user === "admin" && req.body.pass === "admin") {
    res.send("Welcome admin! (identifiants par défaut detectés)");
  } else {
    res.status(401).send("Unauthorized");
  }
});

// --- Faux phpinfo (disclosure d'infos) ---
app.get("/phpinfo.php", (req, res) => {
  res.type("text/html").send(`
    <h1>PHP Version 5.6.40 (fictif - pour test)</h1>
    <pre>
PHP_VERSION = 5.6.40
SERVER_SOFTWARE = Apache/2.2.34 (Unix)
DOCUMENT_ROOT = /var/www/html
    </pre>
  `);
});

// --- Fichier .env exposé (credentials leak) ---
app.get("/.env", (req, res) => {
  res.type("text/plain").send(
    "DB_HOST=localhost\nDB_USER=root\nDB_PASS=SuperSecret123\nAPI_KEY=sk-fake-1234567890\n"
  );
});

// --- Backup SQL exposé ---
app.get("/backup.sql", (req, res) => {
  res.type("text/plain").send(
    "-- Dump de test\nCREATE TABLE users (id INT, username VARCHAR(50), password VARCHAR(255));\n" +
    "INSERT INTO users VALUES (1, 'admin', '5f4dcc3b5aa765d61d8327deb882cf99');\n"
  );
});

// --- .git/config exposé ---
app.get("/.git/config", (req, res) => {
  res.type("text/plain").send(
    "[core]\n\trepositoryformatversion = 0\n[remote \"origin\"]\n\turl = https://github.com/fake/vulnapp.git\n"
  );
});

// --- server-status façon Apache ---
app.get("/server-status", (req, res) => {
  res.type("text/plain").send("Apache Server Status for localhost\nServer Version: Apache/2.2.34\n");
});

// --- WordPress-like fake pour déclencher des checks Nikto ---
app.get("/wp-login.php", (req, res) => {
  res.send("<h1>WordPress Login (fictif)</h1>");
});

app.get("/wp-config.php.bak", (req, res) => {
  res.type("text/plain").send("define('DB_PASSWORD', 'root');\n");
});

// --- Headers volontairement laxistes ---
app.use((req, res, next) => {
  // Pas de X-Frame-Options
  // Pas de X-Content-Type-Options
  // Pas de Content-Security-Policy
  // Cookie de session sans flags sécurisés
  res.cookie("sessionid", "abc123", { httpOnly: false, secure: false });
  next();
});

// --- Méthodes HTTP ouvertes (PUT/DELETE/TRACE acceptées) ---
app.put("/upload", (req, res) => res.send("PUT accepted"));
app.delete("/upload/:id", (req, res) => res.send("DELETE accepted"));

const PORT = process.env.PORT || 4000;
app.listen(PORT, "0.0.0.0", () => {
  console.log(`Vulnerable test app listening on http://0.0.0.0:${PORT}`);
});
