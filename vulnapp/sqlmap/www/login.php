<?php
$conn = new mysqli(
    getenv('DB_HOST') ?: 'db',
    getenv('DB_USER') ?: 'dvwa',
    getenv('DB_PASS') ?: 'dvwapass',
    getenv('DB_NAME') ?: 'dvwa'
);

if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

if ($_SERVER['REQUEST_METHOD'] == 'POST') {
    $username = $_POST['username'];
    $password = $_POST['password'];

    // VULNERABLE SQL QUERY - NO PREPARED STATEMENTS
    $sql = "SELECT * FROM users WHERE username = '$username' AND password = '$password'";
    $result = $conn->query($sql);

    if ($result && $result->num_rows > 0) {
        echo "<h2>Login successful! Welcome " . htmlspecialchars($username) . "</h2>";
    } else {
        echo "<h2>Invalid credentials</h2>";
    }
} else {
    header('Location: index.php');
}
?>