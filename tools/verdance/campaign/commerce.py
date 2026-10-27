"""Commerce: the catalogue, purchases, deliveries, faction banks, and settling the shop after a sortie.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from verdance.common import WORKSPACE_ROOT, canonical_map_id, load_json, utc_now
from verdance.company.commerce_delivery import delivery_eta, make_pending_delivery, resolve_listing_delivery
from .measure import bp_access
from .roster import ensure_roster

METAL_UNIT = 1000  # 1km$ = 1000 BAR metal


def load_commerce_catalog(workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Broker catalog: Tenebrium, loan packs, fab streams, faction constructors."""
    paths: List[Path] = []
    if workspace is not None:
        paths.append(Path(workspace) / "data" / "commerce" / "commerce_catalog.json")
    here = WORKSPACE_ROOT
    paths.append(here / "data" / "commerce" / "commerce_catalog.json")
    for path in paths:
        if path.exists():
            try:
                data = load_json(path)
                if isinstance(data, dict) and data.get("listings"):
                    return data
            except Exception:
                continue
    return {
        "schemaVersion": "verdance-commerce-catalog/1.0",
        "resource": {
            "id": "tenebrium",
            "startingBalance": {"ashwalkers": 3, "nullmercs": 3},
            "buildFloor": 1,
        },
        "metal": {"startingBalanceK": 7, "unitMetal": 1000},
        "listings": {},
        "sortieRewards": {},
    }


def listing_metal_cost_k(listing: Dict[str, Any]) -> int:
    """Prefer metalCostK; fall back to retired creditCost for one-release compat."""
    if listing.get("metalCostK") is not None:
        return int(listing.get("metalCostK") or 0)
    return int(listing.get("creditCost") or 0)


def _catalog_starting_tenebrium(catalog: Optional[Dict[str, Any]] = None) -> int:
    """Player starting Tnb from catalog (ashwalkers / nullmercs / startingBalancePlayer)."""
    cat = catalog or {}
    resource = cat.get("resource") or {}
    starting = resource.get("startingBalance") or {}
    if "startingBalancePlayer" in resource:
        return max(0, int(resource.get("startingBalancePlayer") or 0))
    for key in ("ashwalkers", "nullmercs", "player"):
        if key in starting:
            return max(0, int(starting.get(key) or 0))
    return 0


def default_commerce_state(catalog: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cat = catalog or {}
    metal_meta = cat.get("metal") or {}
    metal0 = int(metal_meta.get("startingBalanceK", 7) or 0)
    tnb0 = _catalog_starting_tenebrium(cat)
    return {
        "tenebrium": tnb0,
        "metalK": metal0,
        "owned": {},
        "upgrades": {},
        "ledger": [],
    }


def commerce_dest_map_id(state: Dict[str, Any], workspace: Optional[Path] = None) -> str:
    """Best-effort destination map for shop ETA / pending deliveries."""
    def _ok(mid: Optional[str]) -> str:
        if not mid:
            return ""
        # story-engine canonical_map_id(None) returns "unknown" — treat as empty.
        raw = str(mid).strip()
        if not raw or raw.lower() in ("unknown", "none", "null"):
            return ""
        out = canonical_map_id(raw)
        if not out or out == "unknown":
            return ""
        return out

    for key in ("plannedMapId", "activeMapId", "sessionHomeMap"):
        mid = _ok(state.get(key))
        if mid:
            return mid
    # Hub deploy stamp / plan if present beside workspace.
    root = Path(workspace) if workspace is not None else WORKSPACE_ROOT
    for rel in (
        Path("outbox") / "hub_deploy_stamp.latest.json",
        Path("outbox") / "hub_deploy_plan.latest.json",
    ):
        path = root / rel
        if not path.exists():
            continue
        try:
            data = load_json(path)
            if isinstance(data, dict):
                mid = _ok(
                    data.get("mapId")
                    or data.get("deploymentMapId")
                    or (data.get("plan") or {}).get("mapId")
                )
                if mid:
                    return mid
        except Exception:
            continue
    return "greenest_fields"


def ensure_commerce(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Ensure commerce bag; migrate scrap→metalK; retire loans.

    Buy-everything rule: do not auto-grant combat packs. ``starterOwned`` is
    retired (Punch must be purchased). Legacy loan Punch still converts to a
    one-salvo owned package so old saves are not soft-locked.
    """
    catalog = load_commerce_catalog(workspace)
    commerce = state.setdefault("commerce", default_commerce_state(catalog))
    if "tenebrium" not in commerce:
        commerce["tenebrium"] = _catalog_starting_tenebrium(catalog)
    # Migrate retired scrap credits → campaign metal (1km$). scrap÷10 ≈ old pack scale.
    # Live playtest make-good (+9km$ for ~9k end metal never exported) only on scrap migrate.
    if "metalK" not in commerce:
        old_scrap = int(commerce.get("credits") or 0)
        metal_meta = catalog.get("metal") or {}
        start_k = int(metal_meta.get("startingBalanceK", 7) or 0)
        migrated_from_scrap = "credits" in commerce
        commerce["metalK"] = max(start_k, old_scrap // 10) if old_scrap else start_k
        ledger = commerce.setdefault("ledger", [])
        ledger.append({
            "op": "migrate_scrap_to_metal",
            "oldCredits": old_scrap,
            "metalK": commerce["metalK"],
            "at": utc_now(),
        })
        if migrated_from_scrap:
            commerce["metalK"] = int(commerce.get("metalK") or 0) + 9
            ledger.append({
                "op": "metal_playtest_credit",
                "metalK": 9,
                "note": "Make-good for ~9k end metal lost before metalStored export",
                "at": utc_now(),
            })
            flags = state.setdefault("flags", {})
            if isinstance(flags, dict):
                flags["metalPlaytestCreditApplied"] = True
    commerce.pop("credits", None)
    commerce.setdefault("owned", {})
    commerce.setdefault("upgrades", {})
    commerce.setdefault("ledger", [])
    commerce.setdefault("pendingDeliveries", [])
    owned = commerce["owned"]
    listings = catalog.get("listings") or {}

    # Retire Punch-of-Thugs loan: convert to one free non-loan purchase salvo.
    punch = owned.get("punch_of_thugs")
    punch_listing = listings.get("punch_of_thugs") if isinstance(listings.get("punch_of_thugs"), dict) else {}
    if isinstance(punch, dict) and (
        punch.get("loan") or str(punch.get("kind") or "") == "loan_package"
    ):
        owned["punch_of_thugs"] = {
            "qty": max(1, int(punch.get("qty") or 1)),
            "loan": False,
            "unitDef": punch_listing.get("unitDef") or punch.get("unitDef") or "corthud",
            "loanCount": None,
            "loanHealthBaseline": None,
            "spawnHealthFracMin": punch_listing.get("spawnHealthFracMin", 0.85),
            "spawnHealthFracMax": punch_listing.get("spawnHealthFracMax", 1.0),
            "acquiredAtMission": int(punch.get("acquiredAtMission") or state.get("missionNumber", 1) or 1),
            "source": "loan_retire_grant",
            "kind": "purchase_package",
            "count": int(punch_listing.get("count") or 7),
            "delivery": dict(punch_listing.get("delivery") or {}),
        }
        commerce.setdefault("ledger", []).append({
            "op": "loan_retire",
            "listingId": "punch_of_thugs",
            "note": "Punch is now a pawn-launcher purchase (7 Thugs). Prior loan converted to one free salvo.",
            "at": utc_now(),
        })

    for lid, listing in listings.items():
        if not isinstance(listing, dict):
            continue
        if not listing.get("starterOwned"):
            continue
        if lid in owned:
            continue
        owned[lid] = {
            "qty": 1,
            "loan": bool(listing.get("loan")),
            "unitDef": listing.get("unitDef"),
            "loanCount": int(listing.get("count") or 0) if listing.get("loan") else None,
            "loanHealthBaseline": (
                round(
                    (float(listing.get("spawnHealthFracMin") or 0.4)
                     + float(listing.get("spawnHealthFracMax") or 0.5)) * 0.5,
                    3,
                )
                if listing.get("loan")
                else None
            ),
            "spawnHealthFracMin": listing.get("spawnHealthFracMin"),
            "spawnHealthFracMax": listing.get("spawnHealthFracMax"),
            "acquiredAtMission": int(state.get("missionNumber", 1) or 1),
            "source": "starter",
            "kind": listing.get("kind") or "purchase_package",
            "count": listing.get("count"),
            "delivery": dict(listing.get("delivery") or {}),
        }
        commerce.setdefault("ledger", []).append({
            "op": "starter_grant",
            "listingId": lid,
            "at": utc_now(),
        })
    return commerce


def commerce_arc_number(state: Dict[str, Any]) -> int:
    n = int(state.get("missionNumber", 1) or 1)
    if n <= 5:
        return 1
    if n <= 10:
        return 2
    return 3


def listing_available(
    listing_id: str,
    listing: Dict[str, Any],
    state: Dict[str, Any],
    commerce: Dict[str, Any],
) -> Tuple[bool, str]:
    if not listing:
        return False, "unknown listing"
    owned = commerce.get("owned") or {}
    upgrades = commerce.get("upgrades") or {}
    kind = str(listing.get("kind") or "")
    if kind == "printer_upgrade" and listing_id in upgrades:
        return False, "upgrade already installed"
    if kind == "commander_suit":
        from .suits import has_suit
        if has_suit(state):
            return False, "the company already wears a commander suit"
    if kind == "hero_rental":
        from verdance.company.rentals import can_rent
        ok, why = can_rent(state, str(listing.get("heroId") or ""))
        if not ok:
            return False, why
    if kind in ("unit_printer", "loan_package") and listing_id in owned:
        return False, "already owned"
    if kind == "hero_contract":
        hid = str(listing.get("heroId") or "")
        heroes = ((state.get("roster") or {}).get("heroes") or [])
        for h in heroes:
            if isinstance(h, dict) and str(h.get("heroId")) == hid and str(h.get("status")) != "locked":
                return False, f"hero {hid} already on the company"
        if listing_id in owned:
            return False, "contract already signed"
    if listing.get("starterOwned") and listing.get("loan") and listing_id in owned:
        return False, "already owned (starter loan)"
    req = listing.get("requires")
    if req and req not in owned:
        return False, f"requires {req}"
    arc_min = int(listing.get("arcMin") or 1)
    if commerce_arc_number(state) < arc_min:
        return False, f"arc {arc_min}+ only"
    rep = state.get("reputation") or {}
    for faction, need in (listing.get("repMin") or {}).items():
        have = float(rep.get(faction, 0) or 0)
        if have < float(need):
            return False, f"need {faction} rep >= {need} (have {have:.0f})"
    tcost = int(listing.get("tenebriumCost") or 0)
    if listing.get("builds") and tcost < 1:
        tcost = 1
    mcost = listing_metal_cost_k(listing)
    if int(commerce.get("tenebrium") or 0) < tcost:
        return False, f"need {tcost} Tenebrium (have {commerce.get('tenebrium', 0)})"
    if int(commerce.get("metalK") or 0) < mcost:
        return False, f"need {mcost}×1km$ metal (have {commerce.get('metalK', 0)})"
    return True, "ok"


def purchase_listing(
    state: Dict[str, Any],
    listing_id: str,
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Buy/install a catalog listing. Mutates state commerce. Returns receipt."""
    catalog = load_commerce_catalog(workspace)
    commerce = ensure_commerce(state, workspace)
    listing = (catalog.get("listings") or {}).get(listing_id)
    if not isinstance(listing, dict):
        return {"ok": False, "error": "unknown listing", "listingId": listing_id}
    ok, reason = listing_available(listing_id, listing, state, commerce)
    if not ok:
        return {"ok": False, "error": reason, "listingId": listing_id}
    tcost = int(listing.get("tenebriumCost") or 0)
    if listing.get("builds") and tcost < 1:
        tcost = 1
    mcost = listing_metal_cost_k(listing)
    commerce["tenebrium"] = int(commerce.get("tenebrium") or 0) - tcost
    commerce["metalK"] = int(commerce.get("metalK") or 0) - mcost
    kind = str(listing.get("kind") or "purchase_package")
    if kind == "hero_rental":
        # A hero for one drop (verdance.company.rentals); not in the bag, in the company.
        from verdance.company.rentals import rent
        rent(state, listing, workspace)
    elif kind == "commander_suit":
        # Cortex's suit, loaned for one fight (verdance.campaign.suits): the walker is fielded for the
        # next drop in Cortex's body, and goes back to Cortex at homecoming (settle_commerce_after_sortie).
        from .suits import grant_suit, LOAN
        grant_suit(state, listing.get("unitDef") or "corcom", LOAN)
    elif kind == "hero_contract":
        roster = ensure_roster(state)
        heroes = roster.setdefault("heroes", [])
        hid = str(listing.get("heroId") or "hero")
        existing = next((h for h in heroes if isinstance(h, dict) and str(h.get("heroId")) == hid), None)
        hero_rec = {
            "heroId": hid,
            "name": str(listing.get("heroName") or hid.title()),
            "unitDef": str(listing.get("unitDef") or "legscout"),
            "missionCritical": False,
            "status": "active",
            "xp": 0.15,
            "timesWounded": 0,
            "campaignXp": 0.0,
            "peakBarXp": 0.15,
            "level": 1,
            "rank": "Runner",
            "trait": str(listing.get("trait") or "wheelie_mentor"),
            "traits": ["wheelie_mentor", "scout_tech"],
            "unlock": {"listingId": listing_id, "rep": "nullmercs"},
        }
        if existing:
            existing.update({k: v for k, v in hero_rec.items() if k != "heroId"})
            existing["status"] = "active"
        else:
            heroes.append(hero_rec)
        chars = state.setdefault("characters", {})
        if hid not in chars:
            chars[hid] = {
                "id": hid,
                "name": hero_rec["name"],
                "faction": "nullmercs",
                "unitDef": hero_rec["unitDef"],
                "xp": 0,
                "player": True,
                "home": None,
                "status": "active",
                "wounds": 0,
                "scars": [],
            }
        else:
            chars[hid]["player"] = True
            chars[hid]["status"] = "active"
        commerce.setdefault("owned", {})[listing_id] = {
            "qty": 1,
            "kind": "hero_contract",
            "heroId": hid,
            "acquiredAtMission": int(state.get("missionNumber", 1) or 1),
            "source": "purchase",
        }
    elif kind == "printer_upgrade":
        commerce.setdefault("upgrades", {})[listing_id] = {
            "installedAtMission": int(state.get("missionNumber", 1) or 1),
            "requires": listing.get("requires"),
            "metalIncomeBonus": listing.get("metalIncomeBonus"),
            "energyIncomeBonus": listing.get("energyIncomeBonus"),
            "nanoDef": listing.get("nanoDef"),
            "nanoCount": listing.get("nanoCount"),
        }
    else:
        prev = (commerce.get("owned") or {}).get(listing_id) or {}
        qty = int(prev.get("qty") or 0) + 1 if kind == "purchase_package" else 1
        delivery = resolve_listing_delivery(listing, listing_id, workspace)
        dest = commerce_dest_map_id(state, workspace)
        eta = delivery_eta(
            listing=listing,
            listing_id=listing_id,
            dest_map_id=dest,
            workspace=workspace,
        )
        commerce.setdefault("owned", {})[listing_id] = {
            "qty": qty,
            "loan": bool(listing.get("loan")),
            "unitDef": listing.get("unitDef") or listing.get("factoryDef"),
            "loanCount": int(listing.get("count") or 0) if listing.get("loan") else None,
            "loanHealthBaseline": (
                round(
                    (float(listing.get("spawnHealthFracMin") or 0.4)
                     + float(listing.get("spawnHealthFracMax") or 0.5)) * 0.5,
                    3,
                )
                if listing.get("loan")
                else None
            ),
            "acquiredAtMission": int(state.get("missionNumber", 1) or 1),
            "source": "purchase",
            "kind": kind,
            "product": listing.get("product"),
            "factoryDef": listing.get("factoryDef"),
            "seedCount": listing.get("seedCount"),
            "metalIncome": listing.get("metalIncome"),
            "energyIncome": listing.get("energyIncome"),
            "count": listing.get("count"),
            "spawnHealthFracMin": listing.get("spawnHealthFracMin"),
            "spawnHealthFracMax": listing.get("spawnHealthFracMax"),
            "delivery": delivery,
            "lastEta": {
                "etaSeconds": eta.get("etaSeconds"),
                "etaText": eta.get("etaText"),
                "summary": eta.get("summary"),
                "destMapId": eta.get("destMapId"),
            },
        }
        # Deferred combat packs become pending deliveries (arrive mid-sortie).
        if kind == "purchase_package" and delivery.get("deferred"):
            pending = make_pending_delivery(
                listing_id=listing_id,
                listing=listing,
                dest_map_id=dest,
                qty=1,
                workspace=workspace,
                mission_number=int(state.get("missionNumber", 1) or 1),
            )
            if pending:
                # Unique id per purchase event.
                pending["id"] = f"pd_{listing_id}_{int(state.get('missionNumber', 1) or 1)}_{qty}_{len(commerce.get('pendingDeliveries') or [])}"
                commerce.setdefault("pendingDeliveries", []).append(pending)
    commerce.setdefault("ledger", []).append({
        "op": "purchase",
        "listingId": listing_id,
        "tenebriumCost": tcost,
        "metalCostK": mcost,
        "at": utc_now(),
        "missionNumber": int(state.get("missionNumber", 1) or 1),
    })
    receipt = {
        "ok": True,
        "listingId": listing_id,
        "tenebriumCost": tcost,
        "metalCostK": mcost,
        "tenebriumLeft": commerce["tenebrium"],
        "metalKLeft": commerce["metalK"],
    }
    if kind == "purchase_package":
        eta = delivery_eta(
            listing=listing,
            listing_id=listing_id,
            dest_map_id=commerce_dest_map_id(state, workspace),
            workspace=workspace,
        )
        receipt["delivery"] = {
            "mode": eta.get("mode"),
            "etaSeconds": eta.get("etaSeconds"),
            "etaText": eta.get("etaText"),
            "summary": eta.get("summary"),
            "sourceLabel": eta.get("sourceLabel"),
            "routeLabels": eta.get("routeLabels"),
            "deferred": bool(eta.get("deferred")),
        }
    return receipt


def build_commerce_intent(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Serialize commerce bag + shop shelf + deploy specs for the mission compiler.

    map_web packs go to pendingDeliveries (mid-sortie arrival).
    pawn_launcher / constructors / fabs go to deploy (t=0 kit).
    """
    catalog = load_commerce_catalog(workspace)
    commerce = ensure_commerce(state, workspace)
    listings = catalog.get("listings") or {}
    owned = commerce.get("owned") or {}
    upgrades = commerce.get("upgrades") or {}
    dest = commerce_dest_map_id(state, workspace)
    shop: List[Dict[str, Any]] = []
    for lid, listing in listings.items():
        if not isinstance(listing, dict):
            continue
        ok, reason = listing_available(lid, listing, state, commerce)
        tcost = int(listing.get("tenebriumCost") or 0)
        if listing.get("builds") and tcost < 1:
            tcost = 1
        eta = delivery_eta(
            listing=listing,
            listing_id=lid,
            dest_map_id=dest,
            workspace=workspace,
        )
        shop.append({
            "id": lid,
            "label": listing.get("label") or lid,
            "blurb": listing.get("blurb") or "",
            "kind": listing.get("kind"),
            "tenebriumCost": tcost,
            "metalCostK": listing_metal_cost_k(listing),
            "builds": bool(listing.get("builds")),
            "available": ok,
            "blockedReason": None if ok else reason,
            "repMin": listing.get("repMin") or {},
            "arcMin": int(listing.get("arcMin") or 1),
            "tags": list(listing.get("tags") or []),
            "count": listing.get("count") or listing.get("seedCount"),
            "delivery": {
                "mode": eta.get("mode"),
                "deferred": bool(eta.get("deferred")),
                "sourceLabel": eta.get("sourceLabel"),
                "sourceBlurb": eta.get("sourceBlurb"),
                "etaSeconds": eta.get("etaSeconds"),
                "etaText": eta.get("etaText"),
                "summary": eta.get("summary"),
                "routeLabels": eta.get("routeLabels"),
                "travelMinutes": eta.get("travelMinutes"),
                "landNear": eta.get("landNear"),
            },
        })
    deploy: List[Dict[str, Any]] = []
    pending: List[Dict[str, Any]] = []
    # Carry explicit pending queue first.
    for item in commerce.get("pendingDeliveries") or []:
        if isinstance(item, dict) and str(item.get("status") or "in_transit") == "in_transit":
            pending.append(copy.deepcopy(item))

    pending_listing_ids = {str(p.get("listingId")) for p in pending}

    for lid, rec in owned.items():
        if not isinstance(rec, dict):
            continue
        listing = listings.get(lid) or {}
        kind = str(rec.get("kind") or listing.get("kind") or "purchase_package")
        delivery = resolve_listing_delivery(listing, lid, workspace)
        deferred = bool(delivery.get("deferred")) and kind == "purchase_package"

        if kind in ("loan_package", "purchase_package") or (
            listing.get("unitDef") and kind not in ("unit_printer", "constructor", "hero_contract",
                                                    "hero_rental", "commander_suit")
        ):
            unit_def = rec.get("unitDef") or listing.get("unitDef")
            count = int(rec.get("loanCount") or rec.get("count") or listing.get("count") or 0)
            qty = int(rec.get("qty") or 1)
            if kind == "purchase_package":
                count = int(listing.get("count") or count or 0) * max(1, qty)
            if unit_def and count > 0:
                hmin = float(rec.get("spawnHealthFracMin") or listing.get("spawnHealthFracMin") or 1.0)
                hmax = float(rec.get("spawnHealthFracMax") or listing.get("spawnHealthFracMax") or 1.0)
                hfrac = round((hmin + hmax) * 0.5, 3)
                if deferred:
                    # Synthesize pending from owned if purchase did not queue yet
                    # (e.g. migrated crash/punch from older saves).
                    if lid not in pending_listing_ids:
                        syn = make_pending_delivery(
                            listing_id=lid,
                            listing=listing or {
                                "unitDef": unit_def,
                                "count": int(listing.get("count") or count // max(1, qty)),
                                "spawnHealthFracMin": hmin,
                                "spawnHealthFracMax": hmax,
                                "label": listing.get("label") or lid,
                                "delivery": delivery,
                            },
                            dest_map_id=dest,
                            qty=qty,
                            workspace=workspace,
                            mission_number=int(state.get("missionNumber", 1) or 1),
                        )
                        if syn:
                            syn["count"] = count
                            pending.append(syn)
                            pending_listing_ids.add(lid)
                else:
                    deploy.append({
                        "listingId": lid,
                        "kind": "package",
                        "unitDef": unit_def,
                        "count": count,
                        "healthFrac": hfrac,
                        "healthFracMin": hmin,
                        "healthFracMax": hmax,
                        "loan": bool(rec.get("loan") or listing.get("loan")),
                        "packageTag": lid,
                        "label": listing.get("label") or lid,
                    })
        if kind == "unit_printer" or listing.get("factoryDef"):
            metal = float(rec.get("metalIncome") or listing.get("metalIncome") or 8)
            energy = float(rec.get("energyIncome") or listing.get("energyIncome") or 40)
            for _uid, up in upgrades.items():
                if not isinstance(up, dict):
                    continue
                if up.get("requires") and up.get("requires") != lid:
                    continue
                metal += float(up.get("metalIncomeBonus") or 0)
                energy += float(up.get("energyIncomeBonus") or 0)
            deploy.append({
                "listingId": lid,
                "kind": "unit_printer",
                "factoryDef": rec.get("factoryDef") or listing.get("factoryDef") or "corlab",
                "product": rec.get("product") or listing.get("product") or "corak",
                "seedCount": int(rec.get("seedCount") or listing.get("seedCount") or 4),
                "metalIncome": metal,
                "energyIncome": energy,
                "label": listing.get("label") or lid,
            })
            for uid, up in upgrades.items():
                if not isinstance(up, dict):
                    continue
                if up.get("requires") and up.get("requires") != lid:
                    continue
                nano = up.get("nanoDef") or "cornanotc"
                ncount = int(up.get("nanoCount") or 0)
                if ncount > 0:
                    deploy.append({
                        "listingId": uid,
                        "kind": "nano",
                        "unitDef": nano,
                        "count": ncount,
                        "label": "Fab build power",
                    })
        if kind == "constructor" or listing.get("kind") == "constructor":
            unit_def = rec.get("unitDef") or listing.get("unitDef")
            count = int(rec.get("count") or listing.get("count") or 1) * int(rec.get("qty") or 1)
            if unit_def and count > 0:
                deploy.append({
                    "listingId": lid,
                    "kind": "constructor",
                    "unitDef": unit_def,
                    "count": count,
                    "label": listing.get("label") or lid,
                })
    access = bp_access(state)
    # Keep bag queue aligned with what the compiler will seed.
    commerce["pendingDeliveries"] = copy.deepcopy(pending)
    metal_meta = catalog.get("metal") or {}
    # Operating allotment only — campaign metalK stays home and export ADDs.
    field_start_k = int(metal_meta.get("fieldStartMetalK") or 1)
    if field_start_k < 0:
        field_start_k = 0
    field_start_e = int(metal_meta.get("fieldStartEnergy") or 3000)
    if field_start_e < 0:
        field_start_e = 0
    return {
        "tenebrium": int(commerce.get("tenebrium") or 0),
        "metalK": int(commerce.get("metalK") or 0),
        # Explicit: bag does not enter BAR; gadget reads these for field seed.
        "metalKBrought": 0,
        "fieldStartMetalK": field_start_k,
        "metalKFieldStart": field_start_k,
        "fieldStartEnergy": field_start_e,
        "resourceLabel": ((catalog.get("resource") or {}).get("label") or "Tenebrium"),
        "metalLabel": metal_meta.get("label") or "Metal",
        "metalShortLabel": metal_meta.get("shortLabel") or "1km$",
        "metalUnit": int(metal_meta.get("unitMetal") or METAL_UNIT),
        "buildFloor": int((catalog.get("resource") or {}).get("buildFloor") or 1),
        "bpAccess": access,
        "owned": copy.deepcopy(owned),
        "upgrades": copy.deepcopy(upgrades),
        "shop": shop,
        "deploy": deploy,
        "pendingDeliveries": pending,
        "destMapId": dest,
        "arc": commerce_arc_number(state),
        "notes": (
            "Tenebrium is black-hole metal (scarce since the Generic Disaster). "
            "Anything that builds costs ≥1. Concurrent BP ceiling = 150 × access Tnb. "
            "Campaign metal bag stays home; sortie export floor(endMetal/1000) ADDS "
            "to faction 1km$ (fieldStart netted out). Living Tnb build-stakes refund on exfil. "
            "Combat packs ship via map-web / pawn launcher with field ETAs."
        ),
    }


def ensure_faction_banks(state: Dict[str, Any]) -> Dict[str, Any]:
    """World paint: per-faction Tenebrium banks (Armada crisis = 0)."""
    flags = state.setdefault("worldFlags", {})
    flags.setdefault("armadaTenebriumCrisis", True)
    banks = state.setdefault("factionBanks", {})
    banks.setdefault("armada", 0 if flags.get("armadaTenebriumCrisis", True) else 3)
    banks.setdefault("cortex", int(banks.get("cortex", 2) or 2))
    banks.setdefault("nullmercs", int((state.get("commerce") or {}).get("tenebrium") or 0))
    banks.setdefault("ashwalkers", int((state.get("commerce") or {}).get("tenebrium") or 0))
    if flags.get("armadaTenebriumCrisis", True):
        banks["armada"] = 0
    return banks


def settle_commerce_after_sortie(
    state: Dict[str, Any],
    result: Dict[str, Any],
    success: bool,
    clean: bool,
    zone_flipped: bool,
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Award Tenebrium + bank end-metal as 1km$; settle loan packages."""
    catalog = load_commerce_catalog(workspace)
    commerce = ensure_commerce(state, workspace)
    ensure_faction_banks(state)
    rewards = catalog.get("sortieRewards") or {}
    rng_seed = hashlib.md5(
        f"{result.get('resultKey')}|{state.get('missionNumber')}|commerce".encode("utf-8")
    ).hexdigest()

    def _roll(tag: str) -> float:
        h = hashlib.md5(f"{rng_seed}|{tag}".encode("utf-8")).hexdigest()
        return int(h[:8], 16) / float(0xFFFFFFFF)

    gained_t = 0
    gained_k = 0
    notes: List[str] = []

    def _award_range(spec: Any, tag: str) -> int:
        if not isinstance(spec, dict) or not spec:
            return 0
        chance = float(spec.get("chance", 1.0) or 1.0)
        if _roll(tag + ":p") > chance:
            return 0
        lo = int(spec.get("min", 0) or 0)
        hi = int(spec.get("max", lo) or lo)
        if hi < lo:
            hi = lo
        if lo == hi:
            return lo
        span = hi - lo + 1
        return lo + int(_roll(tag + ":v") * span) % span

    # Tenebrium is the hyper-rare build currency (owner call, 2026-10-27): it comes only from reclaiming
    # what builders leave behind. Metal comes mostly from the stockpile extracted below (build storage,
    # reclaim everything); a won sortie only tops it up (sortieRewards.metalOnVictory, in 1k units).
    # Capturing ground pays nothing of either.
    award_k = 0
    if success:
        award_k += _award_range(rewards.get("metalOnVictory") or {}, "mv")
    if award_k:
        commerce["metalK"] = int(commerce.get("metalK") or 0) + award_k
        notes.append(f"+{award_k}×1km$ metal (mission reward)")
        commerce.setdefault("ledger", []).append({"op": "mission_reward", "metalK": award_k, "at": utc_now(),
                                                  "missionNumber": int(state.get("missionNumber", 1) or 1)})

    # Campaign metal export: floor(end stockpile / 1000). Prefer metalKExtracted.
    # Bag stays HOME — export ADDS to faction totals (never replaces the bag).
    metal_unit = int(((catalog.get("metal") or {}).get("unitMetal")) or METAL_UNIT)
    try:
        metal_stored = float(result.get("metalStored"))
    except (TypeError, ValueError):
        metal_stored = -1.0
    try:
        metal_k_field = int(float(result.get("metalKExtracted")))
    except (TypeError, ValueError):
        metal_k_field = -1
    if metal_k_field >= 0:
        raw_export_k = metal_k_field
    elif metal_stored >= 0:
        raw_export_k = int(math.floor(metal_stored / float(metal_unit)))
    else:
        raw_export_k = 0
    try:
        metal_k_brought = int(float(result.get("metalKBrought")))
    except (TypeError, ValueError):
        metal_k_brought = -1  # unknown / legacy result
    try:
        metal_k_field_start = int(float(result.get("metalKFieldStart") or 0))
    except (TypeError, ValueError):
        metal_k_field_start = 0
    if metal_k_field_start < 0:
        metal_k_field_start = 0

    # WO-043c: end-of-sortie bank is authoritative liquid stock.
    # Lua refunds living build-stakes into bank on exfil before writing this.
    try:
        loot_field = int(float(result.get("tenebriumLooted") or 0))
    except (TypeError, ValueError):
        loot_field = 0
    try:
        bank_end = int(float(result.get("tenebriumBank") or -1))
    except (TypeError, ValueError):
        bank_end = -1
    try:
        spent_field = int(float(result.get("tenebriumSpent") or 0))
    except (TypeError, ValueError):
        spent_field = 0
    try:
        lost_field = int(float(result.get("tenebriumLost") or 0))
    except (TypeError, ValueError):
        lost_field = 0
    try:
        living_stakes = int(float(result.get("tenebriumLivingStakes") or result.get("tenebriumInvested") or 0))
    except (TypeError, ValueError):
        living_stakes = 0

    if bank_end >= 0:
        # Live bank (incl. exfil stake refund) is authoritative; awards stack on top.
        prev = int(commerce.get("tenebrium") or 0)
        award_extra = gained_t  # nothing mints Tnb any more; kept 0 so the bank is the field's
        commerce["tenebrium"] = bank_end + award_extra
        if bank_end != prev:
            notes.append(f"Tenebrium bank {prev} → {bank_end} (field)")
        if award_extra:
            notes.append(f"+{award_extra} Tenebrium (sortie awards)")
        if loot_field:
            notes.append(f"reclaimed {loot_field} Tnb from wrecks/shards")
        if living_stakes:
            notes.append(f"exfil refunded {living_stakes} Tnb from living builds")
        if spent_field:
            notes.append(f"spent {spent_field} Tnb on build-power units (net after exfil refund)")
        if lost_field:
            notes.append(f"lost {lost_field} Tnb (wrecks vaporized)")
        gained_t = award_extra + max(0, bank_end - prev)
    else:
        if loot_field > 0:
            gained_t += loot_field
            notes.append(f"+{loot_field} Tenebrium (reclaim loot)")
        if living_stakes > 0:
            gained_t += living_stakes
            notes.append(f"+{living_stakes} Tenebrium (exfil living-stake refund)")
        commerce["tenebrium"] = int(commerce.get("tenebrium") or 0) + gained_t
        if gained_t and loot_field <= 0 and living_stakes <= 0:
            notes.append(f"+{gained_t} Tenebrium")
        elif gained_t and (loot_field > 0 or living_stakes > 0) and gained_t > (loot_field + living_stakes):
            notes.append(f"+{gained_t - loot_field - living_stakes} Tenebrium (sortie awards)")

    # Metal: ADD export to faction bag. Never replace.
    # - New path (metalKBrought==0): bag stayed home; ADD max(0, export - fieldStart).
    # - Legacy path (metalKBrought>0): bag was dumped onto map; ADD net delta
    #   (export - brought) so spending bag metal still reduces the bag.
    prev_metal_k = int(commerce.get("metalK") or 0)
    if metal_k_field >= 0 or metal_stored >= 0 or raw_export_k:
        if metal_k_brought > 0:
            delta_k = int(raw_export_k) - metal_k_brought
            commerce["metalK"] = max(0, prev_metal_k + delta_k)
            mode = "legacy_delta"
        else:
            # Net out operating field seed so unused allotment does not inflate bag.
            export_k = max(0, int(raw_export_k) - metal_k_field_start)
            delta_k = export_k
            commerce["metalK"] = prev_metal_k + export_k
            mode = "add"
        if delta_k != 0:
            sign = "+" if delta_k > 0 else ""
            notes.append(
                f"{sign}{delta_k}×1km$ metal ({mode}; export={raw_export_k} "
                f"fieldStart={metal_k_field_start} brought={metal_k_brought if metal_k_brought >= 0 else '?'}; "
                f"bag {prev_metal_k}→{commerce['metalK']})"
            )
            commerce.setdefault("ledger", []).append({
                "op": "metal_export_add" if mode == "add" else "metal_field_settle",
                "metalK": commerce["metalK"],
                "prevMetalK": prev_metal_k,
                "metalKExtracted": int(raw_export_k),
                "metalKFieldStart": metal_k_field_start,
                "metalKBrought": metal_k_brought if metal_k_brought >= 0 else None,
                "metalStored": int(metal_stored) if metal_stored >= 0 else None,
                "deltaK": delta_k,
                "mode": mode,
                "at": utc_now(),
            })
        gained_k = delta_k
    elif raw_export_k:
        commerce["metalK"] = prev_metal_k + raw_export_k
        notes.append(f"+{raw_export_k}×1km$ metal (end stock {int(metal_stored) if metal_stored >= 0 else '?'})")
        commerce.setdefault("ledger", []).append({
            "op": "metal_bank",
            "metalK": raw_export_k,
            "metalStored": metal_stored if metal_stored >= 0 else None,
            "at": utc_now(),
            "missionNumber": int(state.get("missionNumber", 1) or 1),
        })
        gained_k = raw_export_k
    # Persistent world flag: Armada Tenebrium crisis (spent on decoy farms).
    state.setdefault("worldFlags", {})["armadaTenebriumCrisis"] = True
    if result.get("armadaTenebriumCrisis") is False:
        state["worldFlags"]["armadaTenebriumCrisis"] = False

    survivors = result.get("playerSurvivors") if isinstance(result.get("playerSurvivors"), dict) else {}
    # loanUnitHp: unitDef -> { count, avgHpFrac, minHpFrac } (result contract v2)
    loan_hp = result.get("loanUnitHp") if isinstance(result.get("loanUnitHp"), dict) else {}
    listings = catalog.get("listings") or {}
    rep = state.setdefault("reputation", {})
    for lid, rec in list((commerce.get("owned") or {}).items()):
        if not isinstance(rec, dict) or not rec.get("loan"):
            continue
        listing = listings.get(lid) or {}
        unit_def = str(rec.get("unitDef") or listing.get("unitDef") or "")
        loan_n = int(rec.get("loanCount") or listing.get("count") or 0)
        if not unit_def or loan_n <= 0:
            continue
        alive = int(float(survivors.get(unit_def) or 0))
        # Loaned quality: default smoking packs ship ~0.4 avg HP; "better shape"
        # means count OK and avgHpFrac improved (or unknown HP → count-only legacy).
        loaned_frac = float(rec.get("healthFrac") or listing.get("healthFrac") or 0.42)
        hp_info = loan_hp.get(unit_def) if isinstance(loan_hp.get(unit_def), dict) else {}
        avg_hp = hp_info.get("avgHpFrac")
        quality_ok = True
        if avg_hp is not None:
            try:
                quality_ok = float(avg_hp) >= min(0.95, loaned_frac + 0.08)
            except (TypeError, ValueError):
                quality_ok = True
        count_ok = alive >= loan_n
        returned_well = success and count_ok and quality_ok
        if returned_well:
            bonus = rewards.get("loanReturnBonus") or {}
            k_bonus = int(bonus.get("metalK") if bonus.get("metalK") is not None else bonus.get("credits") or 0)
            # Legacy scrap tip (±25) → clamp to ±1 km$ if still using credits key.
            if bonus.get("metalK") is None and abs(k_bonus) > 5:
                k_bonus = 1 if k_bonus > 0 else -1
            r_bonus = float(bonus.get("nullmercRep") or 0)
            commerce["metalK"] = int(commerce.get("metalK") or 0) + k_bonus
            gained_k += k_bonus
            if r_bonus:
                rep["nullmercs"] = round(float(rep.get("nullmercs") or 0) + r_bonus, 2)
            if float(bonus.get("tenebriumChance") or 0) > 0 and _roll(f"loan:{lid}") < float(bonus["tenebriumChance"]):
                commerce["tenebrium"] = int(commerce.get("tenebrium") or 0) + 1
                gained_t += 1
                notes.append(f"loan {lid}: broker tips 1 Tenebrium")
            shape = f"avgHp={avg_hp}" if avg_hp is not None else "count-only"
            notes.append(f"loan {lid}: returned {alive}/{loan_n} in better shape ({shape})")
            commerce.setdefault("ledger", []).append({
                "op": "loan_return_ok",
                "listingId": lid,
                "alive": alive,
                "loanCount": loan_n,
                "avgHpFrac": avg_hp,
                "at": utc_now(),
            })
        elif (not success) or alive < max(1, int(math.ceil(loan_n * 0.5))) or (success and count_ok and not quality_ok):
            pen = rewards.get("loanBreachPenalty") or {}
            # Soft quality miss: half penalty if count ok but still smoking.
            soft = success and count_ok and not quality_ok
            k_pen = int(pen.get("metalK") if pen.get("metalK") is not None else pen.get("credits") or 0)
            if pen.get("metalK") is None and abs(k_pen) > 5:
                k_pen = -1 if k_pen < 0 else 1
            r_pen = float(pen.get("nullmercRep") or 0)
            if soft:
                k_pen = int(math.floor(k_pen * 0.5)) if k_pen else 0
                r_pen = r_pen * 0.5
                notes.append(f"loan {lid}: quality miss ({alive}/{loan_n}, avgHp={avg_hp})")
            else:
                notes.append(f"loan {lid}: breach ({alive}/{loan_n} returned)")
            commerce["metalK"] = max(0, int(commerce.get("metalK") or 0) + k_pen)
            gained_k += k_pen
            if r_pen:
                rep["nullmercs"] = round(float(rep.get("nullmercs") or 0) + r_pen, 2)
            commerce.setdefault("ledger", []).append({
                "op": "loan_return_quality_miss" if soft else "loan_return_breach",
                "listingId": lid,
                "alive": alive,
                "loanCount": loan_n,
                "avgHpFrac": avg_hp,
                "at": utc_now(),
            })

    # Rented heroes go back to Cortex; who came home is remembered for the campaign-end unlock.
    from verdance.company.rentals import settle as _settle_rentals
    from .suits import return_loan as _return_suit
    if _return_suit(state):
        notes.append("the Cortex suit went back to Cortex")
        commerce.setdefault("owned", {}).pop("cortex_commander_suit", None)
    home = _settle_rentals(state, result)
    if home:
        notes.append("rentals home: " + ", ".join(home))

    # What the shop sells is for one drop (owner, 2026-10-26): a bought package or constructor came
    # down with this sortie and is spent. Anything of it that lifts home is the company's by then
    # only if it was not hired (the exfil manifest keeps hired units out of the reserve).
    for lid, rec in list((commerce.get("owned") or {}).items()):
        if not isinstance(rec, dict) or rec.get("loan"):
            continue
        if str(rec.get("kind") or "purchase_package") in ("purchase_package", "package", "constructor"):
            commerce["owned"].pop(lid, None)
            commerce.setdefault("ledger", []).append({
                "op": "drop_spent", "listingId": lid, "qty": rec.get("qty"),
                "at": utc_now(), "missionNumber": int(state.get("missionNumber", 1) or 1),
            })
            notes.append(f"{lid}: spent on this drop")

    gained_k += award_k     # the mission reward, on top of what the field exported
    commerce.setdefault("ledger", []).append({
        "op": "sortie_settle",
        "tenebriumGained": gained_t,
        "metalKGained": gained_k,
        "success": success,
        "zoneFlipped": zone_flipped,
        "at": utc_now(),
        "missionNumber": int(state.get("missionNumber", 1) or 1),
    })
    if len(commerce.get("ledger") or []) > 80:
        commerce["ledger"] = commerce["ledger"][-60:]
    # The army itself travels in the company reserve (verdance.company.reserve), not here.

    # Keep faction bank mirror for null/ash in sync with commerce bag.
    banks = ensure_faction_banks(state)
    banks["nullmercs"] = int(commerce.get("tenebrium") or 0)
    banks["ashwalkers"] = int(commerce.get("tenebrium") or 0)
    return {
        "tenebrium": commerce["tenebrium"],
        "metalK": commerce["metalK"],
        "gainedTenebrium": gained_t,
        "gainedMetalK": gained_k,
        "notes": notes,
        "factionBanks": banks,
    }


__all__ = [
    "METAL_UNIT",
    "_catalog_starting_tenebrium",
    "build_commerce_intent",
    "commerce_arc_number",
    "commerce_dest_map_id",
    "default_commerce_state",
    "ensure_commerce",
    "ensure_faction_banks",
    "listing_available",
    "listing_metal_cost_k",
    "load_commerce_catalog",
    "purchase_listing",
    "settle_commerce_after_sortie",
]
