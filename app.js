fetch("qr_export.json")
  .then(r => r.json())
  .then(data => {

    document.getElementById("updated").innerText =
      "Ultimo aggiornamento: " + data.updated_at;

    render("value", data.value, "💎 VALUE BET");
    render("corner", data.corner, "🔥 TOP CORNER");
    render("hot", data.hot, "⭐ TOP MATCH");
  });


function render(id, matches, title) {

  const container = document.getElementById(id);
  container.innerHTML = "";

  matches.forEach(m => {

    const c = document.createElement("div");
    c.className = "card";

    c.innerHTML = `
      <div class="league">${m.league} – ${m.kickoff}</div>
      <div class="match">${m.home} vs ${m.away}</div>

      <div class="badges">
        ${id === "hot" ? "<span class='hot'>TOP</span>" : ""}
        ${id === "value" ? "<span class='value'>VALUE</span>" : ""}
        ${id === "corner" ? "<span class='corner'>CORNER</span>" : ""}
      </div>

      <div class="market">⚽ Over 2.5: ${(m.markets.over25*100).toFixed(1)}%</div>
      <div class="market">🚩 Over 9.5 corner: ${(m.markets.corners95*100).toFixed(1)}%</div>
      <div class="market">🟨 Casa cards: ${(m.markets.cards_home*100).toFixed(1)}%</div>
      <div class="market">💎 DNB Casa: ${(m.markets.dnb_home*100).toFixed(1)}%</div>
    `;

    container.appendChild(c);

  });
}
