async function loadData(){

 const r = await fetch("qr_export.json?"+Date.now());
 const data = await r.json();

 document.getElementById("updated").innerText =
   "Ultimo aggiornamento: "+data.updated_at;

 render(data.corner,"corner");
 render(data.value,"value");
 render(data.hot,"hot");
}

function confBadge(p){
 if(p>0.62) return `<span class="badge high">ALTA</span>`;
 if(p>0.55) return `<span class="badge mid">MEDIA</span>`;
 return `<span class="badge low">SPECULATIVA</span>`;
}

function render(list,id){

 const box=document.getElementById(id);
 box.innerHTML="";

 if(!list || list.length===0){
   box.innerHTML="<p>Nessun evento attivo.</p>";
   return;
 }

 list.forEach(ev=>{

  const d=document.createElement("div");
  d.className="card";

  d.innerHTML=`
   <div class="match">${ev.home} - ${ev.away}</div>
   <div>${ev.league}</div>
   <div>🕒 ${ev.kickoff}</div>

   <div class="market">${ev.market}</div>

   <div>
     Prob ${(ev.prob*100).toFixed(1)}%
     ${confBadge(ev.prob)}
   </div>

   <div class="details">
     ${ev.quota_min?`Quota minima: ${ev.quota_min}<br>`:""}
     ${ev.expected_total?`Corner stimati: ${ev.expected_total}<br>`:""}
     ${ev.reason?`🧠 ${ev.reason}<br>`:""}
     Algoritmo BetBrain AI.
   </div>

   <a class="button" target="_blank" href="https://www.vincitu.it">
     GIOCA
   </a>
  `;

  d.onclick=()=>toggle(d);

  box.appendChild(d);
 });
}

function toggle(card){
 const det=card.querySelector(".details");
 det.style.display = det.style.display==="block"?"none":"block";
}

setInterval(loadData,60000);
window.onload=loadData;
