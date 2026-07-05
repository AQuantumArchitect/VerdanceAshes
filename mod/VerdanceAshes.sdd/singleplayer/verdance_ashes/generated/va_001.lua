return {
  schemaVersion = "verdance-playable/1.0-alpha",
  campaignId = "verdance_ashes",
  missionId = "va_002",
  missionNumber = 2,
  deploymentMapId = "eye_of_horus",
  deploymentZoneId = "EOH_NW_CRATER_CAMP",
  extractionZoneId = "EOH_NW_CRATER_CAMP",
  pathSignal = "B",
  title = "Verdance Alpha: Eye of Horus - Alpha Campaign Player",
  zone = "Eye of Horus",
  objective = {
    id = "EOH_CORTEX_DEALER_RELAY",
    kind = "strike_relay",
    requiredFrames = 21600,
    description = "Destroy the Cortex dealer relay",
    targetZoneId = "EOH_SE_CORTEX_POCKET",
    extractionZoneId = "EOH_NW_CRATER_CAMP"
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
      unitDefName = "armwar",
      xp = 0.504,
      morale = 80,
      loyalty = 85,
      stress = 6,
      autonomy = 0.35,
      commandMode = "hybrid"
    }
  },
  storyIntent = {
    schemaVersion = "verdance-mission-intent/1.0",
    campaignId = "verdance_ashes",
    missionId = "va_002",
    missionNumber = 2,
    mapId = "eye_of_horus",
    deploymentZoneId = "EOH_NW_CRATER_CAMP",
    extractionZoneId = "EOH_NW_CRATER_CAMP",
    objective = "strike_relay",
    objectiveTarget = {
      id = "EOH_CORTEX_DEALER_RELAY",
      kind = "strike_relay",
      label = "Destroy the Cortex dealer relay",
      targetZoneId = "EOH_SE_CORTEX_POCKET"
    },
    storyTags = {
      "tempo",
      "eye_of_horus"
    },
    persistentBaseRehydrate = {},
    offscreenPressureSummary = {
      maxHazard = 0,
      maxFortification = 0,
      maxMilitary = 0,
      zones = {}
    },
    expectedEnemyScale = {
      low = 3000,
      center = 6000,
      high = 10000,
      basis = "default_no_zone_memory"
    },
    hazardPolicy = "none",
    economy = {
      difficultyCoefficient = 1.206
    },
    environment = {
      mapFamily = "tempo",
      campaignClockMinutes = 5
    },
    dialogueHooks = {
      "tempo",
      "eye_of_horus"
    },
    storyReason = "Current graph pressure favors a short objective sortie over full map conquest."
  },
  simulation = {
    variantId = "alpha_player",
    variantLabel = "Alpha Campaign Player",
    ai = {
      {
        name = "SimpleAI(Cortex Target)",
        shortName = "SimpleAI",
        team = 1,
        version = "<not-versioned>"
      }
    }
  },
  playableSetup = {
    enabled = true,
    mapId = "eye_of_horus",
    variantId = "alpha_player",
    variantLabel = "Alpha Campaign Player",
    notes = "Human-controlled alpha campaign sortie generated from next_mission_intent.json.",
    forces = {
      {
        id = "player_deployment",
        label = "Player Deployment - EOH_NW_CRATER_CAMP",
        teamID = 0,
        side = "Legion",
        role = "player_anchor",
        base = {
          x = 0.15,
          z = 0.15
        },
        recipe = "legion_sortie_start",
        groups = {
          {
            id = "legion_sortie_start",
            units = {
              {
                unitDefName = "legmex",
                count = 3,
                atMetalSpots = true,
                dx = -140,
                dz = 120,
                spacing = 120
              },
              {
                unitDefName = "legwin",
                count = 4,
                dx = 120,
                dz = 160,
                spacing = 90
              },
              {
                unitDefName = "legsolar",
                count = 2,
                dx = 240,
                dz = 80,
                spacing = 90
              },
              {
                unitDefName = "leglht",
                count = 3,
                dx = -120,
                dz = -120,
                spacing = 120
              },
              {
                unitDefName = "legcen",
                count = 4,
                dx = 80,
                dz = -210,
                spacing = 95
              },
              {
                unitDefName = "legjav",
                count = 2,
                dx = 260,
                dz = -230,
                spacing = 110
              }
            }
          }
        }
      },
      {
        id = "primary_objective_force",
        label = "Destroy the Cortex dealer relay",
        teamID = 1,
        side = "Cortex",
        role = "objective_target",
        base = {
          x = 0.84,
          z = 0.84
        },
        recipe = "cortex_sortie_target",
        groups = {
          {
            id = "cortex_sortie_target",
            units = {
              {
                unitDefName = "cormex",
                count = 4,
                atMetalSpots = true,
                dx = -140,
                dz = 120,
                spacing = 120
              },
              {
                unitDefName = "corwin",
                count = 5,
                dx = 120,
                dz = 120,
                spacing = 90
              },
              {
                unitDefName = "corsolar",
                count = 3,
                dx = 230,
                dz = 0,
                spacing = 90
              },
              {
                unitDefName = "corllt",
                count = 5,
                dx = -160,
                dz = -170,
                spacing = 120
              },
              {
                unitDefName = "corrl",
                count = 2,
                dx = 20,
                dz = -190,
                spacing = 130
              },
              {
                unitDefName = "corgator",
                count = 7,
                dx = -40,
                dz = -300,
                spacing = 90
              }
            }
          }
        }
      }
    }
  },
  balance = {
    playerTeamID = 0,
    playerController = "human",
    simFrames = 5400,
    target = "BARb hard/aggressive should clear or gain advantage; SimpleAI should stall."
  }
}

