
const UPGRADE_SEED = [
  ["Gate A2","Capacité","Débloque une nouvelle porte active",750000,1],
  ["Gate A3-A4","Capacité","Deux portes supplémentaires",1400000,1],
  ["Parking courte durée","Accès","Capacité parking et revenus annexes",300000,5],
  ["Parking premium","Accès","Services premium et revenus",600000,5],
  ["Sûreté terminal","Sécurité","Scanners, lignes, personnel et débit",450000,10],
  ["Police aux frontières","Sécurité","E-gates, guichets et trafic international",650000,10],
  ["Pompiers / ARFF","Sécurité","Temps de réponse et catégorie opérationnelle",900000,8],
  ["Toilettes","Passagers","Propreté, capacité et satisfaction",180000,10],
  ["Duty Free","Commercial","Surface commerciale et revenus",550000,10],
  ["Restauration","Commercial","Cafés, restaurants et satisfaction",420000,10],
  ["Lounge Business","Premium","Confort premium et prestige",850000,8],
  ["Lounge First","Premium","Expérience flagship",1600000,6],
  ["Bagages","Opérations","Tri, fiabilité et correspondances",700000,10],
  ["Catering","Opérations","Service à bord et turnaround",750000,10],
  ["Maintenance légère","Opérations","Disponibilité de flotte",1000000,8],
  ["Centre équipages","Personnel","Repos, briefing, fatigue et rotations",800000,8],
  ["Operations Control Center","OPS","NOTAM, déroutements et recovery réseau",1250000,10]
];

const defaultState = {cash:8500000,rep:72,hubLevel:1,upgrades:{}};
UPGRADE_SEED.forEach(([n,c,d,cost,max])=>defaultState.upgrades[n]={category:c,desc:d,cost,level:0,max});
let state;
try { state = JSON.parse(localStorage.getItem("skyline_v02")) || structuredClone(defaultState); }
catch { state = structuredClone(defaultState); }

function save(){localStorage.setItem("skyline_v02",JSON.stringify(state));}
function money(v){return v>=1000000?(v/1000000).toFixed(2).replace(".",",")+" M€":Math.round(v/1000)+" k€";}
function score(){return Object.values(state.upgrades).reduce((s,u)=>s+u.level,0);}
function hubLevelFromScore(s){
  const cuts=[4,8,13,19,27,36,46,58,72,88,106];
  return 1+cuts.filter(x=>s>=x).length;
}
function imageLevel(level){if(level<=2)return 1;if(level<=5)return 4;if(level<=9)return 8;return 12;}
function gates(){
  let g=1;
  if(state.upgrades["Gate A2"].level)g++;
  if(state.upgrades["Gate A3-A4"].level)g+=2;
  g+=Math.max(0,state.hubLevel-4)*2;
  return Math.min(40,g);
}
function toast(msg){
  const el=document.getElementById("toast");el.textContent=msg;el.classList.add("show");
  setTimeout(()=>el.classList.remove("show"),2200);
}
function updateUI(){
  state.hubLevel=hubLevelFromScore(score());
  const g=gates();
  document.getElementById("cashTop").textContent=money(state.cash);
  document.getElementById("repTop").textContent=state.rep+" ★";
  document.getElementById("hubTop").textContent="CDG · Niv. "+state.hubLevel;
  document.getElementById("hubPill").textContent="NIVEAU "+state.hubLevel;
  document.getElementById("cashPill").textContent=money(state.cash);
  document.getElementById("hubImage").src="/static/assets/hub_level_"+imageLevel(state.hubLevel)+".png";
  document.getElementById("gatesMetric").textContent=g;
  document.getElementById("depMetric").textContent=2+g*4;
  document.getElementById("paxMetric").textContent=(220+g*410).toLocaleString("fr-FR");
  document.getElementById("progressLabel").textContent=state.hubLevel+" / 12";
  document.getElementById("hubProgress").style.width=(state.hubLevel/12*100)+"%";
  renderUpgrades();
  save();
}
function price(u){return Math.round(u.cost*(1+0.38*u.level));}
function buy(name){
  const u=state.upgrades[name]; if(!u || u.level>=u.max)return;
  const p=price(u);
  if(state.cash<p){toast("Fonds insuffisants");return;}
  state.cash-=p;u.level++;
  if(["Premium","Passagers","Sécurité"].includes(u.category))state.rep=Math.min(100,state.rep+1);
  toast(name+" amélioré · niveau "+u.level);
  updateUI();
}
const cats=["Toutes",...new Set(UPGRADE_SEED.map(x=>x[1]))];
let filter="Toutes";
function renderFilters(){
  const f=document.getElementById("filters");f.innerHTML="";
  cats.forEach(c=>{const b=document.createElement("button");b.textContent=c;b.className=c===filter?"active":"";
    b.addEventListener("click",()=>{filter=c;renderFilters();renderUpgrades();});f.appendChild(b);});
}
function renderUpgrades(){
  const list=document.getElementById("upgradeList"); if(!list)return; list.innerHTML="";
  Object.entries(state.upgrades).filter(([n,u])=>filter==="Toutes"||u.category===filter).forEach(([name,u])=>{
    const el=document.createElement("article");el.className="upgrade-item";
    const p=price(u), pct=u.level/u.max*100;
    el.innerHTML=`<div class="u-head"><div><h3>${name}</h3><small>${u.category}</small></div><b>${u.level}/${u.max}</b></div>
      <p>${u.desc}</p><div class="progress"><i style="width:${pct}%"></i></div>
      <div class="u-bottom"><span class="cost">${u.level>=u.max?"MAX":money(p)}</span><button ${u.level>=u.max?"disabled":""}>${u.level>=u.max?"Terminé":"Acheter"}</button></div>`;
    el.querySelector("button").addEventListener("click",()=>buy(name));list.appendChild(el);
  });
}
function nav(to){
  document.querySelectorAll(".view").forEach(v=>v.classList.remove("active"));
  document.getElementById(to+"View").classList.add("active");
  document.querySelectorAll("[data-nav]").forEach(b=>b.classList.toggle("active",b.dataset.nav===to));
  window.scrollTo({top:0,behavior:"smooth"});
}
document.querySelectorAll("[data-nav]").forEach(b=>b.addEventListener("click",()=>nav(b.dataset.nav)));
document.querySelectorAll("[data-upgrade]").forEach(b=>b.addEventListener("click",()=>{nav("upgrades");filter=state.upgrades[b.dataset.upgrade]?.category||"Toutes";renderFilters();renderUpgrades();}));
document.getElementById("divertBtn").addEventListener("click",()=>{
  document.getElementById("divertResult").textContent="✓ SKY775 rerouté vers Ottawa-YOW. Rotations suivantes recalculées.";
  toast("Déroutement exécuté par OPS");
});
document.getElementById("notifyBtn").addEventListener("click",()=>toast("2 alertes OPS actives"));
renderFilters();updateUI();
if("serviceWorker" in navigator){window.addEventListener("load",()=>navigator.serviceWorker.register("/sw.js").catch(()=>{}));}
