<!DOCTYPE html>
<html>
<head>
    <title>Login - Vulnerable App</title>
    <style>
        body { font-family: Arial; margin: 50px; }
        input { padding: 10px; margin: 5px; }
    </style>
</head>
<body>
    <h1>Vulnerable Login Page (SQLi Demo)</h1>
    <form action="login.php" method="POST">
        <input type="text" name="username" placeholder="Username" required><br>
        <input type="password" name="password" placeholder="Password" required><br>
        <button type="submit">Login</button>
    </form>
    <p><a href="users.php">View all users (vulnerable)</a></p>
</body>
</html>