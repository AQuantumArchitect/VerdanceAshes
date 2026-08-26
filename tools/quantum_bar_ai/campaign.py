"""Full Verdance campaign — three arcs playable by the player-proxy bot.

Arc 1 (va_001–005): strike team / no-base raids  — see first_arc.py
Arc 2 (va_006–010): expand / tempo / first eco
Arc 3 (va_011–015): siege / wilds / multipressure climax

SimTruth stays private. PlayerFacingCard is the only legal mission start view.

After build, ``enrich_campaign`` attaches campaign solution_space (width curve)
and lane geometry for seize/hold maps (Koom 3–5).
"""
from __future__ import annotations

from typing import Any

from .fair_obs import PlayerFacingCard
from .first_arc import ArcMission, SimTruth, build_first_arc
from .campaign_manifold import CampaignRho, attach_solution_spaces, solution_space_for
from .lane_war import geometry_for_map


def build_second_arc(*, difficulty: float = 1.0) -> list[ArcMission]:
    """Mid campaign: Tabula maneuver, eco expansion, tempo lanes."""
    d = max(0.5, float(difficulty))
    return [
        ArcMission(
            map_id="tabula",
            deploy_zone="TAB_SOUTH_RAMP",
            objective_id="TAB_MID_GATE",
            card=PlayerFacingCard(
                id="va_006",
                title="Tabula — Hold the Gate",
                kind="hold_plateau",
                map_name="Tabula",
                deploy_label="South ramp shelf",
                objective_label="Mid plateau gate",
                extraction_label="North tier mouth",
                situation=(
                    "Tiered plateau. The mid gate is the only clean climb. "
                    "Armada watches the ramps; Null mercs skirmish the lower shelf."
                ),
                objective_text="Take and hold the mid plateau gate until the mark completes.",
                how_to_win=(
                    "Maneuver, do not slug. Probe ramps, flank the gate, hold the mark. "
                    "Soft clock ~12 min."
                ),
                threats="Elevated guns. Frontal climb is expensive. Routes exist left and right.",
                allies="Thin Null merc screen on the lower shelf.",
                plain_objective="hold_plateau: Mid plateau gate",
                soft_clock_minutes=12,
                no_base_building=True,
                briefing_lines=[
                    {"speaker": "ketha", "text": "Don't charge the stairs. Own the angle, then the gate."},
                    {"speaker": "vane", "text": "Plateau fights reward patience. Then they reward violence."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=1.0 * d,
                fortified=True,
                duration_ticks=120,
                player_start_strength=0.74,
                enemy_start_strength=0.54,
                difficulty_label="standard",
            ),
        ),
        ArcMission(
            map_id="tabula",
            deploy_zone="TAB_MID_GATE",
            objective_id="TAB_NORTH_SHELF",
            card=PlayerFacingCard(
                id="va_007",
                title="Tabula — Expand the Shelf",
                kind="eco_expand",
                map_name="Tabula",
                deploy_label="Mid gate (continue)",
                objective_label="North shelf eco footprint",
                extraction_label="North tier mouth",
                situation=(
                    "Gate is yours. Now plant metal and energy on the north shelf. "
                    "This is the first real expand — constructors matter."
                ),
                objective_text="Grow eco on the north shelf and hold it against the counter.",
                how_to_win=(
                    "Build mex and energy. Keep a front. When income is fat enough and the "
                    "shelf is held, extract. Soft clock ~14 min."
                ),
                threats="Armada probes. If you pure-raid without eco, the clock eats you.",
                allies="None on shelf. You are the main effort.",
                plain_objective="eco_expand: North shelf footprint",
                soft_clock_minutes=14,
                no_base_building=False,
                briefing_lines=[
                    {"speaker": "ketha", "text": "Plant something that pays. Then defend the plant."},
                    {"speaker": "vane", "text": "Wind and solars first if the plateau is hungry."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=0.98 * d,
                fortified=False,
                duration_ticks=130,
                player_start_strength=0.72,
                enemy_start_strength=0.5,
                difficulty_label="standard",
            ),
        ),
        ArcMission(
            map_id="greenest_fields",
            deploy_zone="GF_SE_STAGING",
            objective_id="GF_CONVERTER_GRID",
            card=PlayerFacingCard(
                id="va_008",
                title="Greenest Fields — Converter Crawl",
                kind="eco_expand",
                map_name="Greenest Fields",
                deploy_label="Southeast Staging",
                objective_label="Converter grid dominance",
                extraction_label="Central grassland",
                situation=(
                    "No metal on the green — only converters. Race Armada on energy-to-metal. "
                    "Build wind/solar, feed converters, starve theirs."
                ),
                objective_text="Out-eco Armada on the converter grid and wreck their farm.",
                how_to_win=(
                    "Energy first, then conversion. Raid their eco once yours is stable. "
                    "Soft clock ~12 min."
                ),
                threats="Armada converter farm + light perimeter. No mex for anyone.",
                allies="None.",
                plain_objective="eco_expand: Converter grid",
                soft_clock_minutes=12,
                no_base_building=False,
                briefing_lines=[
                    {"speaker": "ketha", "text": "Metal is a lie here. Energy is the truth."},
                    {"speaker": "vane", "text": "If our converters stall, we are just infantry in a field."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=0.95 * d,
                fortified=False,
                duration_ticks=115,
                player_start_strength=0.7,
                enemy_start_strength=0.48,
                difficulty_label="standard",
            ),
        ),
        ArcMission(
            map_id="koom_valley",
            deploy_zone="KOOM_NW_GREEN_SHELF",
            objective_id="KOOM_TEMPO_LANE",
            card=PlayerFacingCard(
                id="va_009",
                title="Koom — Tempo Lane",
                kind="seize_lane",
                map_name="Koom Valley",
                deploy_label="Northwest Green Shelf",
                objective_label="Valley tempo lane",
                extraction_label="North Scar Mouth",
                situation=(
                    "Fluid scar again — but this time you bring expand power. "
                    "Own the tempo lane so the next siege has metal behind it."
                ),
                objective_text="Seize and hold the tempo lane; keep eco breathing.",
                how_to_win=(
                    "Push when fat, hold when thin. Mix expand with pressure. Extract when held."
                ),
                threats="Fortified works mid-valley. Residual Armada + Null merc traffic.",
                allies="Null merc contract support — light.",
                plain_objective="seize_lane: Valley tempo lane",
                soft_clock_minutes=12,
                no_base_building=False,
                briefing_lines=[
                    {"speaker": "ketha", "text": "Tempo is a lane you stand on, not a speech."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=1.05 * d,
                fortified=True,
                duration_ticks=125,
                player_start_strength=0.73,
                enemy_start_strength=0.56,
                difficulty_label="hard",
            ),
        ),
        ArcMission(
            map_id="eye_of_horus",
            deploy_zone="EOH_STAGING",
            objective_id="EOH_DEEPER_POCKET",
            card=PlayerFacingCard(
                id="va_010",
                title="Glass — Deeper Pocket",
                kind="strike_relay",
                map_name="Eye of Horus",
                deploy_label="Crater rim staging",
                objective_label="Secondary Cortex node (deeper pocket)",
                extraction_label="West glass shelf",
                situation=(
                    "Second pass under the Eye. Deeper pocket, meaner garrison. "
                    "You may bring a thin eco toehold on the rim — still a strike, not a city."
                ),
                objective_text="Kill the secondary Cortex node. Heroes live. Extract.",
                how_to_win=(
                    "Flank the glass. Optional rim energy only. Do not dig a fortress. "
                    "Soft clock ~12 min."
                ),
                threats="Fortified pocket + Armada overwatch. Frontal is still a grinder.",
                allies="Null merc foothold thinned since last glass run.",
                plain_objective="strike_relay: Secondary Cortex node",
                soft_clock_minutes=12,
                no_base_building=False,
                briefing_lines=[
                    {"speaker": "ketha", "text": "Same glass. Deeper teeth. Flank or die."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=1.08 * d,
                fortified=True,
                duration_ticks=120,
                player_start_strength=0.74,
                enemy_start_strength=0.6,
                difficulty_label="hard",
            ),
        ),
    ]


def build_third_arc(*, difficulty: float = 1.0) -> list[ArcMission]:
    """Late campaign: siege, wilds, multipressure climax."""
    d = max(0.5, float(difficulty))
    return [
        ArcMission(
            map_id="ancient_bastion",
            deploy_zone="AB_SOUTH_APPROACH",
            objective_id="AB_OUTER_RING",
            card=PlayerFacingCard(
                id="va_011",
                title="Bastion — Outer Ring",
                kind="siege",
                map_name="Ancient Bastion",
                deploy_label="South approach plain",
                objective_label="Outer citadel ring",
                extraction_label="South fall-back notch",
                situation=(
                    "Taelith-Armada citadel. Outer ring guns. This is a siege approach — "
                    "build pressure, break the ring, do not charge the keep yet."
                ),
                objective_text="Breach and hold the outer ring long enough to crack it.",
                how_to_win=(
                    "Siege rhythm: eco → pressure → heal → pressure. Flank dead angles. "
                    "Soft clock ~15 min."
                ),
                threats="Heavy fortifications. D8-class denseness. Cortex secondary anchor optional.",
                allies="None. You are the siege.",
                plain_objective="siege: Outer citadel ring",
                soft_clock_minutes=15,
                no_base_building=False,
                briefing_lines=[
                    {"speaker": "ketha", "text": "Walls don't care about speeches. Feed the siege."},
                    {"speaker": "vane", "text": "If we starve for metal here, the bastion eats us."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=1.12 * d,
                fortified=True,
                duration_ticks=140,
                player_start_strength=0.76,
                enemy_start_strength=0.62,
                difficulty_label="hard",
            ),
        ),
        ArcMission(
            map_id="ancient_bastion",
            deploy_zone="AB_OUTER_RING",
            objective_id="AB_INNER_KEEP",
            card=PlayerFacingCard(
                id="va_012",
                title="Bastion — Breach the Keep",
                kind="siege",
                map_name="Ancient Bastion",
                deploy_label="Outer ring (breached)",
                objective_label="Inner keep core",
                extraction_label="South fall-back notch",
                situation=(
                    "Outer ring cracked. Inner keep still breathes. Finish the citadel "
                    "before Armada reconstitutes the ring."
                ),
                objective_text="Destroy the inner keep objective and extract.",
                how_to_win=(
                    "Commit with eco behind you. Heroes must live. Soft clock ~14 min."
                ),
                threats="Last-stand fortify. High dmg density near the keep.",
                allies="None.",
                plain_objective="siege: Inner keep core",
                soft_clock_minutes=14,
                no_base_building=False,
                briefing_lines=[
                    {"speaker": "ketha", "text": "The keep is a mouth. Don't stand in it longer than you need."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=1.15 * d,
                fortified=True,
                duration_ticks=135,
                player_start_strength=0.74,
                enemy_start_strength=0.64,
                difficulty_label="hard",
            ),
        ),
        ArcMission(
            map_id="the_rock_jungle",
            deploy_zone="TRJ_SOUTH_SPINE",
            objective_id="TRJ_WILD_CORRIDOR",
            card=PlayerFacingCard(
                id="va_013",
                title="Rock Jungle — Wild Corridor",
                kind="survive_wilds",
                map_name="The Rock Jungle",
                deploy_label="South limestone spine",
                objective_label="Wild corridor traverse",
                extraction_label="North spire notch",
                situation=(
                    "Limestone labyrinth. Wilds and raptors own the dark. "
                    "Pathing and survival beat pure DPS."
                ),
                objective_text="Traverse the wild corridor and hold the north notch.",
                how_to_win=(
                    "Rally when scattered. Fall back when chewed. Probe chokes. "
                    "Soft clock ~13 min."
                ),
                threats="Raptors / wilds pressure + chokepoint ambushes. Low metal.",
                allies="None reliable.",
                plain_objective="survive_wilds: Wild corridor",
                soft_clock_minutes=13,
                no_base_building=False,
                briefing_lines=[
                    {"speaker": "ketha", "text": "The jungle doesn't hate you. It just doesn't care."},
                    {"speaker": "vane", "text": "Keep the knot tight. Split once and the stones eat us."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=1.05 * d,
                fortified=False,
                duration_ticks=125,
                player_start_strength=0.72,
                enemy_start_strength=0.58,
                difficulty_label="hard",
            ),
        ),
        ArcMission(
            map_id="all_that_simmers",
            deploy_zone="ATS_SOUTH_SHELF",
            objective_id="ATS_CENTRAL_CHOICE",
            card=PlayerFacingCard(
                id="va_014",
                title="Simmers — Choose Your Scar",
                kind="multipressure",
                map_name="All That Simmers",
                deploy_label="South staging shelf",
                objective_label="Central simmer pressure knot",
                extraction_label="North mouth",
                situation=(
                    "Full faction and wild pressure. You must choose: break Armada eco, "
                    "hold the lane, or cut Cortex. The knot only yields to a committed plan."
                ),
                objective_text="Resolve the central pressure knot under multipressure.",
                how_to_win=(
                    "Pick a line early (eco wreck, lane hold, or strike). Mix expand with combat. "
                    "Soft clock ~14 min."
                ),
                threats="ARM + NMC + COR presence. Wilds possible. Pre-built positions.",
                allies="Faction choice may unlock thin merc help — do not count on it.",
                plain_objective="multipressure: Central simmer knot",
                soft_clock_minutes=14,
                no_base_building=False,
                briefing_lines=[
                    {"speaker": "ketha", "text": "Pick a scar and own it. Half-choices drown here."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=1.1 * d,
                fortified=True,
                duration_ticks=135,
                player_start_strength=0.75,
                enemy_start_strength=0.6,
                difficulty_label="hard",
            ),
        ),
        ArcMission(
            map_id="all_that_simmers",
            deploy_zone="ATS_CENTRAL_LANE",
            objective_id="ATS_FINAL_PRESSURE",
            card=PlayerFacingCard(
                id="va_015",
                title="Simmers — Final Pressure",
                kind="multipressure",
                map_name="All That Simmers",
                deploy_label="Central lane (continue)",
                objective_label="Final pressure collapse",
                extraction_label="North mouth",
                situation=(
                    "Campaign climax on the swamp. Collapse the remaining pressure node. "
                    "Roster may be tired. Eco and heroes both matter."
                ),
                objective_text="Collapse the final pressure node and extract clean.",
                how_to_win=(
                    "Finish the objective. Live. Extract. Soft clock ~15 min."
                ),
                threats="Peak multipressure. Clock and attrition both hostile.",
                allies="Whatever reputation bought you — thin at best.",
                plain_objective="multipressure: Final pressure collapse",
                soft_clock_minutes=15,
                no_base_building=False,
                briefing_lines=[
                    {"speaker": "ketha", "text": "Last knot. Don't get poetic. Cut it."},
                    {"speaker": "vane", "text": "If we leave names on this mud, make them theirs."},
                ],
            ),
            truth=SimTruth(
                enemy_scale=1.12 * d,
                fortified=True,
                duration_ticks=140,
                player_start_strength=0.73,
                enemy_start_strength=0.62,
                difficulty_label="climax",
            ),
        ),
    ]


def enrich_campaign(
    missions: list[ArcMission],
    *,
    rho: CampaignRho | None = None,
    n_missions: int | None = None,
    global_index_offset: int = 0,
) -> list[ArcMission]:
    """Attach solution_space (width curve) + lane geometry for line-war maps."""
    rho = rho or CampaignRho()
    n = n_missions if n_missions is not None else max(len(missions), 15)
    for i, m in enumerate(missions):
        idx = global_index_offset + i
        ss = solution_space_for(
            mission_index=idx,
            kind=m.kind,
            n_missions=n,
            rho=rho,
        )
        m.solution_space = ss
        if m.kind in ("seize_lane", "hold_plateau", "multipressure"):
            geo = geometry_for_map(m.map_id, width=ss.width)
            # multipressure on non-lane maps still gets a soft strip geometry
            if geo is None and m.kind == "multipressure":
                from .lane_war import LaneGeometry

                n = 3 if ss.width < 0.5 else (4 if ss.width < 0.75 else 5)
                geo = LaneGeometry(
                    map_id=m.map_id or "multipressure",
                    lane_count=n,
                    labels=[f"Pressure {i+1}" for i in range(n)],
                    primary_index=n // 2,
                )
            m.lane_geometry = geo
    return missions


def build_arc(arc: int, *, difficulty: float = 1.0, enrich: bool = True) -> list[ArcMission]:
    if arc == 1:
        out = build_first_arc(difficulty=difficulty)
        offset = 0
    elif arc == 2:
        out = build_second_arc(difficulty=difficulty)
        offset = 5
    elif arc == 3:
        out = build_third_arc(difficulty=difficulty)
        offset = 10
    else:
        raise ValueError(f"unknown arc {arc}; expected 1..3")
    if enrich:
        enrich_campaign(out, n_missions=15, global_index_offset=offset)
    return out


def build_full_campaign(
    *,
    difficulty: float = 1.0,
    arcs: tuple[int, ...] = (1, 2, 3),
    enrich: bool = True,
    rho: CampaignRho | None = None,
    use_craft: bool | None = None,
) -> list[ArcMission]:
    """Build multi-arc campaign.

    ``use_craft`` (default: auto when ``app/brain/craft_recipe.json`` exists)
    stamps champion solution widths, decoys, per-arc teeth, and lane geometry
    from the overnight gym. Gym loops pass ``use_craft=False`` then re-stamp
    with evolving knobs.
    """
    out: list[ArcMission] = []
    for a in arcs:
        # build without enrich, then enrich once with global indices
        out.extend(build_arc(a, difficulty=difficulty, enrich=False))
    if enrich:
        enrich_campaign(out, rho=rho, n_missions=15, global_index_offset=0)
    if use_craft is None:
        try:
            from .craft_apply import has_recipe

            use_craft = has_recipe()
        except Exception:
            use_craft = False
    if use_craft and out:
        from .craft_apply import stamp_recipe_on_missions

        stamp_recipe_on_missions(out, rho=rho)
    return out


def campaign_meta() -> dict[str, Any]:
    craft_block: dict[str, Any] = {"active": False}
    try:
        from .craft_apply import load_recipe, knobs_from_recipe

        recipe = load_recipe()
        knobs = knobs_from_recipe(recipe=recipe)
        if knobs is not None:
            craft_block = {
                "active": True,
                "stamp": recipe.get("stamp"),
                "craft_score": recipe.get("craft_score"),
                "arc_rates": recipe.get("arc_rates"),
                "overall_win_rate": recipe.get("overall_win_rate"),
                "knobs": knobs.as_dict(),
                "source": recipe.get("source"),
            }
    except Exception:
        pass
    return {
        "schemaVersion": "verdance-campaign-arcs/0.4",
        "manifolds": {
            "proxy": "verdance-player-proxy",
            "campaign": "verdance-campaign-shape",
            "lane": "verdance-lane-war",
        },
        "width_curve": "early narrow/clear vectors → late wide multipath (craft recipe when pinned)",
        "lane_default": {"koom_valley": "3-5 columns", "default_count": 4},
        "craft": craft_block,
        "arcs": {
            "1": {
                "id": "arc_1_strike",
                "title": "First Scar — Strike Team",
                "missions": ["va_001", "va_002", "va_003", "va_004", "va_005"],
                "theme": "no-base raids, hero survival, extract",
                "width_band": "narrow",
            },
            "2": {
                "id": "arc_2_expand",
                "title": "Second Scar — Expand & Tempo",
                "missions": ["va_006", "va_007", "va_008", "va_009", "va_010"],
                "theme": "plateau maneuver, eco expand, tempo lane, deeper strike",
                "width_band": "open",
            },
            "3": {
                "id": "arc_3_climax",
                "title": "Third Scar — Siege & Multipressure",
                "missions": ["va_011", "va_012", "va_013", "va_014", "va_015"],
                "theme": "bastion siege, wild corridor, simmer multipressure climax",
                "width_band": "wide",
            },
        },
        "maps": [
            "greenest_fields",
            "eye_of_horus",
            "all_that_simmers",
            "koom_valley",
            "tabula",
            "ancient_bastion",
            "the_rock_jungle",
        ],
    }
