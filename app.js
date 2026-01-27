// ==========================
// VINCITU AI - FRONT ENGINE
// ==========================

const DATA_URL = "./qr_export.json";

async function loadData() {
  try {
    console.log("📡 Loading feed...");

    const res = await fetch(DATA_URL + "?t=" + Date.now());

    if (!res.ok) {
      throw new Error("HTTP error " + res.status);
    }

    const data = await res.json();

    console.log("✅ Feed OK", data);

    renderSection(data.corner || [], "corner");
    renderSection(data.value || [], "value");
    renderSection(data.hot || [], "hot");

    document.getElementById("updated").innerText =
      "Ultimo aggiornamento: " + data.updated_at;

  } catch (err) {
    console.error("❌ LOAD ERROR:", err);

    document.getElementById("updated").innerText =
      "Errore caricamento feed";
  }
}

function renderSection(events, id) {
  const box = document.getElementById(id);
  box.innerHTML = "";

  if (!events.length) {
    box.innerHTML =
      `<div class="empty">Nessun evento disponibile</div>`;
    return;
  }

  events.forEach(ev => {
    const card = document.createElement("div");
    card.className = "card clickable";

    card.innerHTML = `
      <h3>${ev.home} - ${ev.away}</h3>
      <div class="league">${ev.league}</div>
      <div class="kickoff">🕒 ${ev.kickoff}</div>

      <div class="market">${ev.market}</div>

      <div class="prob">📊 Probabilità: ${(ev.prob * 100).toFixed(1)}%</div>

      ${ev.expected_total ? `<div>📐 Corner attesi: ${ev.expected_total}</div>` : ""}
      ${ev.quota_min ? `<div>💰 Quota min: ${ev.quota_min}</div>` : ""}
    `;

    card.onclick = () => openDetails(ev);

    box.appendChild(card);
  });
}

// ==========================
// POPUP DETTAGLIO EVENTO
// ==========================

function openDetails(ev) {
  alert(
`🔥 ${ev.home} - ${ev.away}

Campionato: ${ev.league}
Orario: ${ev.kickoff}

Mercato: ${ev.market}
Probabilità: ${(ev.prob * 100).toFixed(1)}%

${ev.expected_total ? "Corner attesi: " + ev.expected_total : ""}
${ev.quota_min ? "Quota minima: " + ev.quota_min : ""}
`
  );
}

// ==========================
// AUTO REFRESH
// ==========================

loadData();
setInterval(loadData, 60000);
