const DATA_URL = "qr_export.json";

async function loadData() {
  try {
    const res = await fetch(DATA_URL + "?t=" + Date.now());
    const data = await res.json();

    renderSection("corner", data.corner || []);
    renderSection("value", data.value || []);
    renderSection("hot", data.hot || []);

    const last = document.getElementById("last-update");
    if (last && data.updated_at) {
      last.innerText = "Ultimo aggiornamento: " + data.updated_at;
    }

  } catch (err) {
    console.error("Errore caricamento dati:", err);
  }
}

function renderSection(type, matches) {
  const container = document.getElementById(type + "-container");
  if (!container) return;

  container.innerHTML = "";

  if (!matches.length) {
    container.innerHTML =
      `<div class="empty">Nessun evento disponibile</div>`;
    return;
  }

  matches.forEach(m => {
    const card = document.createElement("div");
    card.className = "match-card";

    card.innerHTML = `
      <div class="league">${m.league}</div>
      <div class="teams">${m.home} vs ${m.away}</div>
      <div class="kickoff">🕒 ${m.kickoff}</div>

      <div class="stats">
        ${m.market ? `<div>📊 ${m.market}</div>` : ""}
        ${m.prob ? `<div>🔥 Probabilità ${Math.round(m.prob * 100)}%</div>` : ""}
        ${m.expected_total ? `<div>🚩 Corner attesi ${m.expected_total}</div>` : ""}
        ${m.cards ? `<div>🟨 Ammoniti ${m.cards}%</div>` : ""}
        ${m.dnb ? `<div>💎 DNB ${m.dnb}%</div>` : ""}
      </div>
    `;

    container.appendChild(card);
  });
}

document.addEventListener("DOMContentLoaded", loadData);
