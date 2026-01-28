// ==============================
// VINCI TU AI — PRO FRONT ENGINE
// ==============================

const DATA_URL = "./qr_export.json";

async function loadData() {
  try {
    const res = await fetch(DATA_URL + "?t=" + Date.now());
    const data = await res.json();

    renderSection(data.corner || [], "corner");
    renderSection(data.value || [], "value");
    renderSection(data.hot || [], "hot");

    document.getElementById("updated").innerText =
      "Ultimo aggiornamento: " + data.updated_at;

  } catch (e) {
    console.error("Errore feed", e);
    document.getElementById("updated").innerText =
      "Errore caricamento feed";
  }
}

function renderSection(events, id) {
  const box = document.getElementById(id);
  box.innerHTML = "";

  if (!events.length) {
    box.innerHTML = `<div class="empty">Nessun evento oggi</div>`;
    return;
  }

  events.forEach(ev => {
    const card = document.createElement("div");
    card.className = "card";

    card.innerHTML = `
      <span class="badge">${ev.league}</span>
      <h3>${ev.home} vs ${ev.away}</h3>
      <div class="league">🕘 ${ev.kickoff}</div>

      ${ev.market ? `<div class="market">${ev.market}</div>` : ""}

      ${ev.prob ? `<div class="prob">Probabilità ${(ev.prob*100).toFixed(1)}%</div>` : ""}

      ${ev.expected_total ? `<div class="prob">Corner attesi ${ev.expected_total}</div>` : ""}
    `;

    box.appendChild(card);
  });
}

loadData();
setInterval(loadData, 120000);
