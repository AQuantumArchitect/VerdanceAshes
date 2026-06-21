return {
  schemaVersion = "0.9-playable",
  campaignId = "verdance_ashes",
  missionId = "va_playable_ats_001",
  missionNumber = 901,
  pathSignal = "B",
  title = "Verdance Playable Slice: All That Simmers",
  zone = "All That Simmers",
  objective = {
    id = "ats_playable_proxy_breakout",
    kind = "playable_proxy",
    requiredFrames = 1800,
    description = "Clans start upper-left. Armada holds upper-right and center. Cortex anchors bottom-right. Raptors infest bottom-left."
  },
  economy = {
    metalIncome = 18,
    energyIncome = 42,
    buildPower = 75
  },
  graph = {
    q0_armada_cortex = 0.23,
    q2_void_structure = 0.15,
    q3_biogenesis_memory = 0.28,
    q4_ai_human = 0.72,
    q6_contested = 0.73,
    q6_independent = 0.34,
    q7_scarcity = 0.98
  },
  reputation = {
    armada = 34,
    cortex = 18,
    clans = 66,
    nullmercs = 47,
    sev = 56
  },
  companions = {
    {
      id = "ketha_rhekk_line",
      displayName = "Ketha of Rhekk's Line",
      unitDefName = "legcen",
      xp = 0.504,
      morale = 80,
      loyalty = 85,
      stress = 6,
      autonomy = 0.35,
      commandMode = "hybrid"
    }
  },
  playableSetup = {
    enabled = true,
    mapId = "all_that_simmers",
    notes = "Proxy layout for fast feel-testing. Coordinates are normalized fractions of the observed 7168x10240 map.",
    forces = {
      {
        id = "clans_upper_left",
        label = "Clans / Player Upper-Left",
        teamID = 0,
        side = "Legion",
        role = "player_anchor",
        base = { x = 0.16, z = 0.18 },
        groups = {
          { id = "clans_base", units = {
            { unitDefName = "legcom", count = 1, dx = 0, dz = 0, spacing = 80 },
            { unitDefName = "legck", count = 2, dx = 140, dz = 40, spacing = 90 },
            { unitDefName = "legmex", count = 3, dx = -160, dz = 120, spacing = 120 },
            { unitDefName = "legwin", count = 4, dx = 120, dz = 180, spacing = 90 },
            { unitDefName = "legsolar", count = 2, dx = 260, dz = 120, spacing = 100 },
            { unitDefName = "leglht", count = 3, dx = -120, dz = -140, spacing = 130 },
            { unitDefName = "legcen", count = 6, dx = 80, dz = -220, spacing = 95, patrolX = 0.34, patrolZ = 0.34 },
          } }
        }
      },
      {
        id = "armada_upper_right",
        label = "Armada Upper-Right Bastion",
        teamID = 1,
        side = "Armada",
        role = "defender",
        base = { x = 0.80, z = 0.18 },
        groups = {
          { id = "armada_bastion", units = {
            { unitDefName = "armcom", count = 1, dx = 0, dz = 0, spacing = 80 },
            { unitDefName = "armmex", count = 3, dx = -160, dz = 120, spacing = 120 },
            { unitDefName = "armwin", count = 5, dx = 130, dz = 120, spacing = 85 },
            { unitDefName = "armsolar", count = 3, dx = 240, dz = -20, spacing = 90 },
            { unitDefName = "armllt", count = 5, dx = -180, dz = -180, spacing = 120 },
            { unitDefName = "armwar", count = 8, dx = -40, dz = -300, spacing = 90, patrolX = 0.58, patrolZ = 0.44 },
          } }
        }
      },
      {
        id = "armada_center_lane",
        label = "Armada Center-Lane Hold",
        teamID = 1,
        side = "Armada",
        role = "center_hold",
        base = { x = 0.57, z = 0.48 },
        groups = {
          { id = "armada_center", units = {
            { unitDefName = "armllt", count = 6, dx = 0, dz = 0, spacing = 130 },
            { unitDefName = "armwar", count = 10, dx = -220, dz = 120, spacing = 85, patrolX = 0.42, patrolZ = 0.58 },
            { unitDefName = "armpw", count = 14, dx = 120, dz = -140, spacing = 75, patrolX = 0.32, patrolZ = 0.62 },
          } }
        }
      },
      {
        id = "cortex_bottom_right",
        label = "Cortex Bottom-Right Island",
        teamID = 2,
        side = "Cortex",
        role = "defender",
        base = { x = 0.82, z = 0.82 },
        groups = {
          { id = "cortex_island", units = {
            { unitDefName = "corcom", count = 1, dx = 0, dz = 0, spacing = 80 },
            { unitDefName = "cormex", count = 3, dx = -120, dz = -100, spacing = 120 },
            { unitDefName = "corwin", count = 5, dx = 120, dz = -80, spacing = 90 },
            { unitDefName = "corsolar", count = 3, dx = 220, dz = 80, spacing = 90 },
            { unitDefName = "corllt", count = 5, dx = -180, dz = 180, spacing = 120 },
            { unitDefName = "corgator", count = 8, dx = -260, dz = -230, spacing = 90, patrolX = 0.62, patrolZ = 0.66 },
            { unitDefName = "corthud", count = 4, dx = -40, dz = -320, spacing = 95, patrolX = 0.56, patrolZ = 0.62 },
          } }
        }
      },
      {
        id = "raptors_bottom_left",
        label = "Raptor Bottom-Left Infestation",
        teamID = 3,
        side = "Raptors",
        role = "wild_pressure",
        base = { x = 0.18, z = 0.78 },
        groups = {
          { id = "raptor_nest", units = {
            { unitDefName = "raptor_hive", count = 1, dx = 0, dz = 0, spacing = 80 },
            { unitDefName = "raptor_turret_basic_t2_v1", count = 4, dx = -160, dz = 80, spacing = 130 },
            { unitDefName = "raptor_land_swarmer_basic_t1_v1", count = 16, dx = 120, dz = -80, spacing = 70, patrolX = 0.35, patrolZ = 0.60 },
            { unitDefName = "raptor_land_swarmer_basic_t2_v1", count = 8, dx = -220, dz = -160, spacing = 80, patrolX = 0.42, patrolZ = 0.58 },
            { unitDefName = "raptor_land_assault_basic_t2_v1", count = 4, dx = 180, dz = 150, spacing = 90, patrolX = 0.48, patrolZ = 0.52 },
          } }
        }
      },
    }
  }
}
