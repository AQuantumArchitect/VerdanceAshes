# Zone scorecard -- current zones

Evidence: **raster**. 7 maps, 102 zones.

Coverage is the share of measured war that lands inside SOME zone; everything else happens on ground no zone describes. Cell-mask zones tile the map, so they read 100% by construction -- on those maps the number to read is the per-zone detail, not coverage.

**How much to trust this.** Behaviour here comes from `legacy_grid` (coarse-early), `legacy_rect` (rectangle-shaped-late). A prior reconstructed from older, coarser telemetry cannot tell a quiet zone from an unvisited one, so "dead" below means *this evidence saw nothing there* -- not that the ground is dead. Run the behaviour survey before treating those as verdicts.

| Map | Zones | Coverage | Dead | Failing | Verdict |
|---|---|---|---|---|---|
| all_that_simmers | 16 | 100% | 2 | 4 | PASS |
| ancient_bastion | 14 | 100% | 2 | 4 | PASS |
| eye_of_horus | 12 | 100% | 1 | 5 | PASS |
| greenest_fields | 12 | 100% | 3 | 3 | PASS |
| koom_valley | 16 | 100% | 2 | 7 | PASS |
| tabula | 16 | 100% | 5 | 9 | PASS |
| the_rock_jungle | 16 | 100% | 0 | 4 | PASS |

## All That Simmers v1.1.1 (all_that_simmers)

Configs: legacy_grid, legacy_rect

| Zone | Role | Cells | Share | Loss | Contested | Water | Build | Anchor | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Central Bastion | fortress | 574 | 20.3% | 0.0% | no | 0.00 | 0.90 | ok | PASS |
| Central Inner Bastion | fortress | 574 | 17.2% | 0.0% | no | 0.01 | 0.88 | ok | PASS |
| Southeast Spillway | spillway | 1266 | 10.4% | 0.0% | no | 0.18 | 0.56 | ok | PASS |
| Northwest Spillway | spillway | 1266 | 9.5% | 0.0% | no | 0.18 | 0.58 | ok | PASS |
| Southwest Gate | gate | 773 | 8.1% | 0.0% | no | 0.00 | 0.92 | ok | FAIL |
| Northwest Shore | shoreline | 530 | 7.6% | 0.0% | yes | 0.26 | 0.65 | ok | PASS |
| Southwest Plateau | plateau | 545 | 6.8% | 0.0% | no | 0.00 | 0.91 | ok | PASS |
| Northeast Gate | gate | 773 | 4.3% | 0.0% | no | 0.00 | 0.90 | ok | FAIL |
| North Shore | shoreline | 557 | 3.2% | 0.0% | yes | 0.08 | 0.80 | ok | PASS |
| Southeast Shore | shoreline | 530 | 2.8% | 0.0% | yes | 0.24 | 0.67 | ok | PASS |
| South Shore | shoreline | 557 | 2.7% | 0.0% | no | 0.21 | 0.64 | ok | PASS |
| Northeast Plateau | plateau | 545 | 2.5% | 0.0% | yes | 0.00 | 0.91 | ok | PASS |
| Southwest Outer Plateau | plateau | 249 | 2.1% | 0.0% | no | 0.00 | 0.85 | ok | PASS |
| Southwest Muster | start | 114 | 1.4% | 0.0% | no | 0.00 | 0.92 | ok | PASS |
| Northeast Outer Plateau | plateau | 249 | 0.6% | 0.0% | yes | 0.00 | 0.85 | ok | FAIL |
| Northeast Muster | start | 114 | 0.5% | 0.0% | yes | 0.00 | 0.93 | ok | FAIL |

Findings:
- **Southwest Gate**: FAIL: role claims a lane but only one bloc ever holds it
- **Northeast Gate**: FAIL: role claims a lane but only one bloc ever holds it
- **Northeast Outer Plateau**: FAIL: dead zone (no measured activity)
- **Northeast Muster**: FAIL: dead zone (no measured activity)

## Ancient Bastion Remake 0.5 (ancient_bastion)

Configs: legacy_grid, legacy_rect

| Zone | Role | Cells | Share | Loss | Contested | Water | Build | Anchor | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Northwest Lane | lane | 1434 | 26.3% | 0.0% | yes | 0.00 | 0.79 | ok | PASS |
| Northwest Bastion | fortress | 478 | 16.8% | 0.0% | yes | 0.00 | 0.66 | ok | PASS |
| Southeast Reserve | reserve | 1702 | 14.1% | 0.0% | no | 0.00 | 0.53 | ok | PASS |
| Southwest Lane | lane | 1434 | 10.4% | 0.0% | yes | 0.00 | 0.79 | ok | PASS |
| Northwest Citadel | citadel | 458 | 10.3% | 0.0% | yes | 0.00 | 0.85 | ok | PASS |
| Northeast Reserve | reserve | 1702 | 4.9% | 0.0% | yes | 0.00 | 0.54 | ok | PASS |
| West Lane | lane | 123 | 3.9% | 0.0% | no | 0.00 | 0.81 | ok | FAIL |
| West Inner Lane | lane | 123 | 3.8% | 0.0% | no | 0.00 | 0.80 | ok | FAIL |
| East Outer Bastion | fortress | 176 | 2.4% | 0.0% | no | 0.00 | 0.68 | ok | PASS |
| East Bastion | fortress | 176 | 2.4% | 0.0% | no | 0.00 | 0.60 | ok | PASS |
| Southeast Citadel | citadel | 237 | 2.2% | 0.0% | yes | 0.00 | 0.90 | ok | PASS |
| Northeast Citadel | citadel | 237 | 2.1% | 0.0% | yes | 0.00 | 0.76 | ok | PASS |
| Southwest Citadel | citadel | 458 | 0.5% | 0.0% | yes | 0.00 | 0.85 | ok | FAIL |
| Southwest Bastion | fortress | 478 | 0.1% | 0.0% | yes | 0.00 | 0.68 | ok | FAIL |

Findings:
- **West Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **West Inner Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **Southwest Citadel**: FAIL: dead zone (no measured activity)
- **Southwest Bastion**: FAIL: dead zone (no measured activity)

## Eye Of Horus 1.7 (eye_of_horus)

Configs: legacy_grid, legacy_rect

| Zone | Role | Cells | Share | Loss | Contested | Water | Build | Anchor | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Northwest Bastion | fortress | 610 | 24.5% | 0.0% | no | 0.00 | 0.63 | ok | PASS |
| Northwest Muster | start | 331 | 22.3% | 0.0% | no | 0.00 | 0.91 | ok | PASS |
| Southeast Bastion | fortress | 610 | 13.6% | 0.0% | no | 0.00 | 0.60 | ok | PASS |
| Northeast Causeway | causeway | 2310 | 8.6% | 0.0% | yes | 0.00 | 0.60 | ok | PASS |
| Southeast Muster | start | 331 | 7.8% | 0.0% | no | 0.00 | 0.87 | ok | PASS |
| Central Inner Gate | gate | 865 | 5.6% | 0.0% | yes | 0.00 | 0.71 | ok | PASS |
| Southwest Causeway | causeway | 2310 | 5.4% | 0.0% | yes | 0.00 | 0.60 | ok | PASS |
| Central Gate | gate | 865 | 5.3% | 0.0% | no | 0.00 | 0.70 | ok | FAIL |
| Central Lane | lane | 237 | 2.5% | 0.0% | no | 0.00 | 0.52 | ok | FAIL |
| Central Inner Lane | lane | 237 | 2.4% | 0.0% | no | 0.00 | 0.47 | ok | FAIL |
| West Lane | lane | 255 | 1.2% | 0.0% | no | 0.00 | 0.66 | ok | FAIL |
| East Lane | lane | 255 | 1.0% | 0.0% | yes | 0.00 | 0.69 | ok | FAIL |

Findings:
- **Central Gate**: FAIL: role claims a lane but only one bloc ever holds it
- **Central Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **Central Inner Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **West Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **East Lane**: FAIL: dead zone (no measured activity)

## Greenest Fields 1.3 (greenest_fields)

Configs: legacy_grid, legacy_rect

| Zone | Role | Cells | Share | Loss | Contested | Water | Build | Anchor | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Northwest Bastion | fortress | 853 | 29.2% | 0.0% | yes | 0.00 | 0.96 | ok | PASS |
| Northwest Muster | start | 392 | 27.5% | 0.0% | no | 0.00 | 0.99 | ok | PASS |
| Northwest Citadel | citadel | 949 | 15.6% | 0.0% | yes | 0.00 | 0.98 | ok | PASS |
| Southwest Bastion | fortress | 853 | 7.7% | 0.0% | no | 0.00 | 0.97 | ok | PASS |
| Southwest Citadel | citadel | 949 | 7.5% | 0.0% | no | 0.00 | 0.98 | ok | PASS |
| Southwest Muster | start | 392 | 4.9% | 0.0% | no | 0.00 | 0.99 | ok | PASS |
| North Plateau | plateau | 515 | 4.1% | 0.0% | yes | 0.00 | 1.00 | ok | PASS |
| Central Gate | gate | 159 | 1.2% | 0.0% | yes | 0.00 | 1.00 | ok | PASS |
| Central Inner Gate | gate | 159 | 1.2% | 0.0% | yes | 0.00 | 1.00 | ok | PASS |
| South Plateau | plateau | 515 | 0.8% | 0.0% | yes | 0.00 | 1.00 | ok | FAIL |
| Northeast Plateau | plateau | 1740 | 0.5% | 0.0% | yes | 0.00 | 0.98 | ok | FAIL |
| Southeast Plateau | plateau | 1740 | 0.0% | 0.0% | no | 0.00 | 0.98 | ok | FAIL |

Findings:
- **South Plateau**: FAIL: dead zone (no measured activity)
- **Northeast Plateau**: FAIL: dead zone (no measured activity)
- **Southeast Plateau**: FAIL: dead zone (no measured activity)

## Koom Valley 3 3.1 (koom_valley)

Configs: legacy_grid, legacy_rect

| Zone | Role | Cells | Share | Loss | Contested | Water | Build | Anchor | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Northwest Muster | start | 1009 | 29.8% | 0.0% | no | 0.00 | 0.68 | ok | PASS |
| Northeast Spillway | spillway | 1001 | 11.4% | 0.0% | yes | 0.00 | 0.70 | ok | PASS |
| Southeast Muster | start | 1009 | 11.0% | 0.0% | yes | 0.00 | 0.66 | ok | PASS |
| Southeast Spillway | spillway | 1001 | 10.7% | 0.0% | no | 0.00 | 0.71 | ok | PASS |
| Southwest Spillway | spillway | 1001 | 7.5% | 0.0% | no | 0.00 | 0.68 | ok | PASS |
| Northwest Spillway | spillway | 1001 | 7.3% | 0.0% | no | 0.00 | 0.71 | ok | PASS |
| Northeast Muster | start | 1009 | 4.6% | 0.0% | no | 0.00 | 0.67 | ok | PASS |
| East Outer Lane | lane | 181 | 3.6% | 0.0% | yes | 0.00 | 0.45 | ok | PASS |
| East Lane | lane | 181 | 3.2% | 0.0% | no | 0.00 | 0.48 | ok | FAIL |
| West Lane | lane | 181 | 2.5% | 0.0% | no | 0.00 | 0.49 | ok | FAIL |
| East Upper Lane | lane | 113 | 2.0% | 0.0% | no | 0.00 | 0.52 | ok | FAIL |
| East Lower Lane | lane | 113 | 2.0% | 0.0% | no | 0.00 | 0.52 | ok | FAIL |
| Southwest Muster | start | 1009 | 1.8% | 0.0% | no | 0.00 | 0.64 | ok | PASS |
| West Outer Lane | lane | 181 | 1.2% | 0.0% | no | 0.00 | 0.50 | ok | FAIL |
| West Upper Lane | lane | 113 | 0.8% | 0.0% | no | 0.00 | 0.58 | ok | FAIL |
| West Lower Lane | lane | 113 | 0.8% | 0.0% | no | 0.00 | 0.49 | ok | FAIL |

Findings:
- **East Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **West Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **East Upper Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **East Lower Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **West Outer Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **West Upper Lane**: FAIL: dead zone (no measured activity)
- **West Upper Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **West Lower Lane**: FAIL: dead zone (no measured activity)
- **West Lower Lane**: FAIL: role claims a lane but only one bloc ever holds it

## Tabula_Remake 1.5 (tabula)

Configs: legacy_grid, legacy_rect

| Zone | Role | Cells | Share | Loss | Contested | Water | Build | Anchor | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Central Inner Spillway | spillway | 1393 | 28.9% | 0.0% | no | 0.05 | 0.78 | ok | PASS |
| Central Spillway | spillway | 1393 | 28.3% | 0.0% | no | 0.07 | 0.78 | ok | PASS |
| Northwest Reserve | reserve | 1222 | 10.2% | 0.0% | no | 0.02 | 0.56 | ok | PASS |
| Northwest Muster | start | 228 | 7.2% | 0.0% | no | 0.00 | 0.93 | ok | PASS |
| Northwest Outer Reserve | reserve | 278 | 5.9% | 0.0% | no | 0.00 | 0.59 | ok | PASS |
| Southeast Reserve | reserve | 1222 | 4.3% | 0.0% | yes | 0.02 | 0.55 | ok | PASS |
| Southwest Causeway | causeway | 1042 | 4.0% | 0.0% | no | 0.22 | 0.40 | ok | FAIL |
| Northwest Causeway | causeway | 190 | 3.6% | 0.0% | no | 0.00 | 0.79 | ok | FAIL |
| Northwest Lane | lane | 113 | 2.2% | 0.0% | no | 0.00 | 0.08 | ok | FAIL |
| West Causeway | causeway | 142 | 1.5% | 0.0% | no | 0.00 | 0.77 | ok | FAIL |
| Northeast Causeway | causeway | 1042 | 1.2% | 0.0% | yes | 0.22 | 0.41 | ok | PASS |
| Southeast Outer Reserve | reserve | 278 | 0.8% | 0.0% | yes | 0.00 | 0.61 | ok | FAIL |
| Southeast Muster | start | 228 | 0.6% | 0.0% | yes | 0.00 | 0.93 | ok | FAIL |
| Southeast Causeway | causeway | 190 | 0.5% | 0.0% | yes | 0.00 | 0.78 | ok | FAIL |
| Southeast Lane | lane | 113 | 0.4% | 0.0% | yes | 0.00 | 0.14 | ok | FAIL |
| East Causeway | causeway | 142 | 0.3% | 0.0% | yes | 0.00 | 0.78 | ok | FAIL |

Findings:
- **Southwest Causeway**: FAIL: role claims a lane but only one bloc ever holds it
- **Northwest Causeway**: FAIL: role claims a lane but only one bloc ever holds it
- **Northwest Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **West Causeway**: FAIL: role claims a lane but only one bloc ever holds it
- **Southeast Outer Reserve**: FAIL: dead zone (no measured activity)
- **Southeast Muster**: FAIL: dead zone (no measured activity)
- **Southeast Causeway**: FAIL: dead zone (no measured activity)
- **Southeast Lane**: FAIL: dead zone (no measured activity)
- **East Causeway**: FAIL: dead zone (no measured activity)

## The Rock Jungle 2.1.1 (the_rock_jungle)

Configs: legacy_grid, legacy_rect

| Zone | Role | Cells | Share | Loss | Contested | Water | Build | Anchor | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Southeast Muster | start | 1731 | 19.6% | 0.0% | no | 0.17 | 0.47 | ok | PASS |
| Northwest Muster | start | 1731 | 18.0% | 0.0% | no | 0.18 | 0.45 | ok | PASS |
| Southwest Shallows | island_chain | 611 | 11.4% | 0.0% | no | 0.73 | 0.09 | ok | WARN |
| Northeast Shallows | island_chain | 611 | 10.4% | 0.0% | no | 0.74 | 0.08 | ok | WARN |
| Northwest Gate | gate | 578 | 6.3% | 0.0% | no | 0.13 | 0.54 | ok | FAIL |
| Southeast Gate | gate | 578 | 6.1% | 0.0% | no | 0.13 | 0.53 | ok | FAIL |
| Central Inner Spillway | spillway | 219 | 4.2% | 0.0% | no | 0.42 | 0.23 | ok | WARN |
| Central Spillway | spillway | 219 | 4.2% | 0.0% | no | 0.43 | 0.23 | ok | WARN |
| Southwest Lane | lane | 812 | 4.0% | 0.0% | no | 0.13 | 0.60 | ok | FAIL |
| Southeast Outer Muster | start | 217 | 3.3% | 0.0% | no | 0.00 | 0.83 | ok | PASS |
| Northeast Lane | lane | 812 | 3.2% | 0.0% | no | 0.14 | 0.58 | ok | FAIL |
| Southwest Rim | rim_control | 278 | 2.6% | 0.0% | no | 0.09 | 0.76 | ok | PASS |
| Northeast Rim | rim_control | 278 | 1.9% | 0.0% | no | 0.09 | 0.78 | ok | PASS |
| West Muster | start | 162 | 1.8% | 0.0% | no | 0.13 | 0.69 | ok | PASS |
| Northwest Outer Muster | start | 217 | 1.7% | 0.0% | yes | 0.00 | 0.83 | ok | PASS |
| East Muster | start | 162 | 1.3% | 0.0% | no | 0.13 | 0.68 | ok | PASS |

Findings:
- **Southwest Shallows**: WARN: role expects building but buildable=0.09
- **Southwest Shallows**: WARN: 73% water inside a land-role zone
- **Northeast Shallows**: WARN: role expects building but buildable=0.08
- **Northeast Shallows**: WARN: 75% water inside a land-role zone
- **Northwest Gate**: FAIL: role claims a lane but only one bloc ever holds it
- **Southeast Gate**: FAIL: role claims a lane but only one bloc ever holds it
- **Central Inner Spillway**: WARN: 42% water inside a land-role zone
- **Central Spillway**: WARN: 43% water inside a land-role zone
- **Southwest Lane**: FAIL: role claims a lane but only one bloc ever holds it
- **Northeast Lane**: FAIL: role claims a lane but only one bloc ever holds it

