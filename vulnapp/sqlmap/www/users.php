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

$id = isset($_GET['id']) ? $_GET['id'] : 1;

// VULNERABLE - BLIND & UNION SQLi possible
$sql = "SELECT * FROM users WHERE id = $id";
$result = $conn->query($sql);

echo "<h1>Users</h1>";
if ($result && $result->num_rows > 0) {
    while($row = $result->fetch_assoc()) {
        echo "<p>ID: " . $row['id'] . " | User: " . htmlspecialchars($row['username']) . "</p>";
    }
} else {
    echo "No user found.";
}
?>
<br>
<a href="index.php">Back to login</a>   