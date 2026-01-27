const DATA_URL = "./qr_export.json";

async function loadData() {
  const res = await fetch(DATA_URL + "?t=" + Date.now());
  const data = await res.json();

  renderSection(data.corner || [], "corner");
  renderSection(data.value || [], "value");
  renderSection(data.hot || [], "hot");

  document.getElementById("updated").innerText =
    "Ultimo aggiornamento: " + data.updated_at;
}

function renderSection(events, id) {
  const box = document.getElementById(id);
  box.innerHTML = "";

  if (!events.length) {
    box.innerHTML = "<div style='color:#666'>Nessun evento disponibile</div>";
    return;
  }

  events.forEach(ev => {
    const d = document.createElement("div");
    d.className = "card";
    d.innerHTML = `
      <h3>${ev.home} - ${ev.away}</h3>
      <div>${ev.league}</div>
      <div>${ev.kickoff}</div>
      <div class="market">${ev.market}</div>
      <div>Probabilità ${(ev.prob * 100).toFixed(1)}%</div>
    `;
    d.onclick = () => openModal(ev);
    box.appendChild(d);
  });
}

function openModal(ev) {
  document.getElementById("m-title").innerText =
    ev.home + " - " + ev.away;

  document.getElementById("m-body").innerHTML = `
    <p><b>${ev.league}</b></p>
    <p>🕒 ${ev.kickoff}</p>
    <p class="market">${ev.market}</p>
    <p>📊 Probabilità ${(ev.prob * 100).toFixed(1)}%</p>
    ${ev.expected_total ? `<p>⚽ Corner attesi ${ev.expected_total}</p>` : ""}
  `;

  document.getElementById("modal").style.display = "flex";
}

function closeModal() {
  document.getElementById("modal").style.display = "none";
}

loadData();
setInterval(loadData, 60000);
