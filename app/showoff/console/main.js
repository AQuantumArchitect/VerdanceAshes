// Boot order for the war-room hub. Everything else is a module with no top-level effects.
import { state, H, commerce, prettyMap, availableMaps, ensureFocusMapAvailable, companySealed } from "./state.js";
import { probeKernel } from "./api.js";
import { $, toast, logLine } from "./render.js";
import { installOverlays } from "./board.js";
import { refreshTheaterForFocus, showDropConfirm, hideDropConfirm, onDropConfirmGo, resetRoute, setMarkMode, onChoice } from "./operations.js";
import { renderCompany, renderShop, sealCompany, toggleCrew, tryBuy, recommendCompany, showCompanyIntro, companyMemberIds, fieldPeople } from "./company.js";
import { raiseCamp, openFoundingSortie, confirmHearthTalk, cancelHearthTalk, refreshCamp, renderCampCard } from "./home.js";
import { showHomecoming, hideHomecoming, pullHubState, pullBarResult, abandonSortie, startResultPoll } from "./homecoming.js";
import { installSystemDrawer, renderRegions, renderQuantum, showCoach, hideCoach } from "./system.js";
import { installShell, renderBadges, renderHeadline, showWorkspace } from "./shell.js";

// Narrow facade — the same surface the shell used to reach the legacy script through.
window.Verdance = {
  snapshot: () => ({ hub: state.hub, plan: state.plan, focusMap: state.focusMap, live: state.hostLive }),
  selectOperation: onChoice,
  focusMap: id => { state.focusMap = id; renderHeadline(); refreshTheaterForFocus(); },
  refresh: pullHubState,
  notify: toast,
  homecoming: showHomecoming, // debrief card (verdict, chips, manifest)
  renderCamp: renderCampCard,
  fieldPeople,
  companyMemberIds,
  recommendCompany,
};

function bindControls() {
  document.querySelectorAll(".mode-btn").forEach(btn => { btn.onclick = () => setMarkMode(btn); });
  $("btn-clear-marks").onclick = resetRoute;
  $("btn-deploy").onclick = showDropConfirm;
  $("drop-confirm-cancel").onclick = hideDropConfirm;
  $("drop-confirm-go").onclick = onDropConfirmGo;
  $("drop-confirm").addEventListener("click", ev => { if (ev.target === $("drop-confirm")) hideDropConfirm(); });
  document.addEventListener("keydown", ev => { if (ev.key === "Escape") hideDropConfirm(); });
  // Hero cards (intro grid, drop squad) toggle through one delegated handler.
  document.addEventListener("click", ev => { const b = ev.target.closest("[data-crew]"); if (b && !b.disabled) toggleCrew(b.dataset.crew); });
  $("shop-list").addEventListener("click", ev => { const b = ev.target.closest("[data-buy]"); if (b && !b.disabled) tryBuy(b.dataset.buy); });
  $("btn-camp-raise").onclick = raiseCamp;
  $("btn-camp-founding").onclick = () => { showWorkspace("operations"); openFoundingSortie(); };
  $("btn-hearth-confirm").onclick = confirmHearthTalk;
  $("btn-hearth-cancel").onclick = cancelHearthTalk;
  $("btn-seal-company-intro").onclick = sealCompany;
  $("recommend-company").onclick = recommendCompany;
  $("btn-open-company-intro").onclick = () => { showCompanyIntro(); toast("Pick 3 packs, then Confirm company", "ok"); };
  $("btn-pull-result").onclick = pullBarResult;
  $("btn-abandon").onclick = abandonSortie;
  $("hc-dismiss").onclick = hideHomecoming;
  $("btn-help").onclick = () => showCoach(true);
  $("coach-go").onclick = () => hideCoach(true);
  $("coach-skip").onclick = () => hideCoach(true);
  // The camp faces are slow; refresh them when Home or Chronicle is opened.
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-workspace]");
    if (b && (b.dataset.workspace === "home" || b.dataset.workspace === "chronicle")) setTimeout(refreshCamp, 0);
  }, true);
  installOverlays();
  installSystemDrawer();
}

async function probeHost() {
  state.hostLive = false;
  state.hostBase = "";
  const hit = await probeKernel();
  if (hit) {
    state.hostLive = true;
    state.hostBase = hit.base;
    state.hostInfo = hit.data;
    if (state.hub.flags) state.hub.flags.deployStub = false;
    logLine(`Campaign connected (${hit.base || location.origin})`);
  } else {
    if (state.hub.flags) state.hub.flags.deployStub = true;
    logLine("Map only — start PLAY.bat and keep its window open to fight in BAR.");
  }
  renderBadges();
  if (state.hostLive) {
    startResultPoll();
    pullHubState().catch(() => {});
  }
}

function boot() {
  if (!window.HUB_STATE) {
    $("title").textContent = "The map is blank";
    $("kicker").textContent = "Rebuild the hub (build_hub_state_v1.py), then open this again.";
    return;
  }
  bindControls();
  // Prefer the recommended sortie theater over home ground so the board matches the primary Drop.
  state.focusMap = (H.node && (H.node.sortieMapId || H.node.regionHint)) || H.sessionHomeMap || (H.regions && H.regions[0] && H.regions[0].mapId) || "greenest_fields";
  ensureFocusMapAvailable();
  renderBadges();
  renderRegions();
  renderShop();
  renderHeadline();
  renderQuantum();
  refreshTheaterForFocus(); // paints the board and the company
  renderCompany();
  logLine(`The map answers · home ${prettyMap(H.sessionHomeMap || "the_rock_jungle")} · ops ${prettyMap(state.focusMap)} · ${availableMaps().length} maps · ${(commerce().shop || []).length} broker listings`);
  installShell();
  probeHost();
  refreshCamp();
  // First open: the company intro owns formation. Defer one tick so a racing pullHubState
  // cannot leave the picker hidden.
  setTimeout(() => { if (!companySealed()) showCompanyIntro(); }, 0);
}

boot();
