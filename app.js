<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8" />
<title>VINCITU AI — Pronostici Live</title>

<meta name="viewport" content="width=device-width, initial-scale=1.0" />

<link rel="stylesheet" href="style.css">

<style>
body {
  background:#0b0b0b;
  color:#fff;
  font-family:Arial, Helvetica, sans-serif;
  margin:0;
  padding:0;
}

header {
  text-align:center;
  padding:30px;
}

.logo {
  font-size:42px;
  font-weight:800;
  border:3px solid red;
  display:inline-block;
  padding:12px 40px;
  color:red;
}

.section-title {
  text-align:center;
  font-size:24px;
  margin:35px 0 15px;
}

.container {
  max-width:1100px;
  margin:auto;
}

.grid {
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(340px,1fr));
  gap:22px;
}

.card {
  background:#141414;
  border-radius:12px;
  padding:18px;
  border:1px solid #2a2a2a;
  cursor:pointer;
  transition:0.25s;
}

.card:hover {
  transform:scale(1.03);
  border-color:#ff3b3b;
}

.badge {
  display:inline-block;
  background:red;
  color:white;
  padding:4px 10px;
  border-radius:6px;
  font-size:12px;
  margin-bottom:6px;
}

.market {
  color:#3cff8f;
  font-weight:700;
}

.small {
  color:#aaa;
  font-size:13px;
}

.details {
  display:none;
  margin-top:12px;
  border-top:1px solid #333;
  padding-top:10px;
}

.updated {
  text-align:center;
  color:#888;
  margin:25px;
}
</style>

</head>

<body>

<header>
  <div class="logo">VINCITU AI</div>
</header>

<div class="container">

<h2 class="section-title">🔥 CORNER AI</h2>
<div id="corner" class="grid"></div>

<h2 class="section-title">💎 VALUE BET</h2>
<div id="value" class="grid"></div>

<h2 class="section-title">⭐ TOP MATCH</h2>
<div id="hot" class="grid"></div>

<div id="updated" class="updated"></div>

</div>

<!-- JS ENGINE -->
<script src="app.js"></script>

</body>
</html>
