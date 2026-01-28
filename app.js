// ===============================
// VINCITU AI - PRO ENGINE v2
// ===============================

const DATA_URL = "./qr_export.json";

async function loadData() {
  try {
    const res = await fetch(DATA_URL + "?t=" + Date.now());
    if (!res.ok) throw new Error(res.status);

    const data = await res.json();

    renderAll(data);

    document.getElementById("updated").innerText =
      "Ultimo aggiornamento: " + data.updated_at;
  } catch (err) {
    console.error("LOAD ERROR", err);
  }
}

// -------------------------------
// AI PICK ENGINE
// -------------------------------

function scorePick(p) {
  let score = 0;

  if (p.over25) score += p.over25 * 100;
  if (p.corner95) score += p.corner95 * 120;
  if (p.dnb) score += p.dnb * 110;
  if (p.cards) score += p.cards * 80;

  return score;
}

// -------------------------------
// RENDER ENGINE
// -------------------------------

function renderAll(data) {
  const container = document.getElementById("all");

  container.innerHTML = "";

  data.matches.forEach(match => {

    const picks = [
      { label: "Over 2.5", value: match.over25 },
      { label: "Over 9.5 Corner", value: match.corner95 },
      { label: "Cards Casa", value: match.cards },
      { label: "DNB Casa", value: match.dnb }
    ].filter(p => p.value);

    picks.forEach(p => p.score = scorePick({
      over25: p.label.includes("Over 2.5") ? p.value : 0,
      corner95: p.label.includes("Corner") ? p.value : 0,
      dnb: p.label.includes("DNB") ? p.value : 0,
      cards: p.label.includes("Cards") ? p.value : 0
    }));

    picks.sort((a,b)=>b.score-a.score);

    const top = picks[0];

    const card = document.createElement("div");
    card.className = "match-card";

    card.innerHTML = `
      <div class="league">${match.league} — ${match.kickoff}</div>
      <h2>${match.home} vs ${match.away}</h2>

      <div class="top-pick">
        🔥 TOP PICK AI<br>
        <span>${top.label}</span>
        <strong>${(top.value*100).toFixed(1)}%</strong>
      </div>

      <div class="others">
        ${picks.slice(1).map(p=>`
          <div>${p.label}: ${(p.value*100).toFixed(1)}%</div>
        `).join("")}
      </div>
    `;

    container.appendChild(card);

  });
}

loadData();
setInterval(loadData, 60000);
