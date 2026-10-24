if not VFS.Include("LuaRules/Configs/va_active.lua") then return {} end -- plain BAR unless the hub launched this
-- Verdance Halberd: Halbard's own Cortex Halberd (corhal) chassis, with the green laser swapped
-- for a pulsing heat ray. Full unitdef (BAR's loader replaces by name; no deep merge).
--
-- The ray is hungry. Its damage, reach and burn time are not fixed here: game_verdance_heatray.lua
-- sets them from how full the company's energy bank is (include/va_heat_ray.lua has the curve).
-- The numbers below are what the ray does with a bank at its baseline; the gadget reads the
-- damage back out of customparams.va_ray_damage so there is one place to change it.

return {
	va_halberd = {
		buildpic = "CORHAL.DDS",
		buildtime = 12900,
		canmove = true,
		collisionvolumeoffsets = "0 1 0",
		collisionvolumescales = "42 12 42",
		collisionvolumetype = "Box",
		corpse = "DEAD",
		energycost = 13000,
		explodeas = "mediumExplosionGeneric",
		footprintx = 3,
		footprintz = 3,
		health = 4350,
		maxacc = 0.02428,
		maxdec = 0.02428,
		maxslope = 16,
		maxwaterdepth = 0,
		metalcost = 640,
		movementclass = "HOVER3",
		name = "Halberd",
		nochasecategory = "VTOL",
		objectname = "Units/CORHAL.s3o",
		script = "Units/CORHAL.cob",
		seismicsignature = 0,
		selfdestructas = "mediumExplosionGenericSelfd",
		sightdistance = 450,
		speed = 45.3,
		turninplace = true,
		turninplaceanglelimit = 90,
		turninplacespeedlimit = 0.9768,
		turnrate = 410,
		usepiececollisionvolumes = 1,
		customparams = {
			model_author = "Beherith",
			normaltex = "unittextures/cor_normal.dds",
			subfolder = "CorHovercraft",
			unitgroup = "weapon",
			va_heat_ray = "1",
		},
		featuredefs = {
			dead = {
				blocking = false,
				category = "corpses",
				collisionvolumeoffsets = "0 1 0",
				collisionvolumescales = "42 18 42",
				collisionvolumetype = "Box",
				damage = 2079,
				featuredead = "HEAP",
				footprintx = 3,
				footprintz = 3,
				height = 20,
				metal = 390,
				object = "Units/corhal_dead.s3o",
				reclaimable = true,
			},
			heap = {
				blocking = false,
				category = "heaps",
				collisionvolumescales = "55.0 4.0 6.0",
				collisionvolumetype = "cylY",
				damage = 1040,
				footprintx = 3,
				footprintz = 3,
				metal = 156,
				object = "Units/cor3X3A.s3o",
				reclaimable = true,
				resurrectable = 0,
			},
		},
		sfxtypes = {
			explosiongenerators = {
				[1] = "custom:waterwake-small-hover",
				[2] = "custom:bowsplash-small-hover",
				[3] = "custom:hover-wake-large",
			},
		},
		sounds = {
			canceldestruct = "cancel2",
			underattack = "warning1",
			cant = {
				[1] = "cantdo4",
			},
			count = {
				[1] = "count6",
				[2] = "count5",
				[3] = "count4",
				[4] = "count3",
				[5] = "count2",
				[6] = "count1",
			},
			ok = {
				[1] = "hovlgok2",
			},
			select = {
				[1] = "hovlgsl2",
			},
		},
		weapondefs = {
			-- The Legion Helios heat ray, turned up: a fat orange beam that pulses (a long beamtime
			-- and a slow reload, like the Helios) instead of the stock tank's quick green flick.
			va_heat_ray = {
				areaofeffect = 12,
				avoidfeature = false,
				beamtime = 0.55,
				corethickness = 0.3,
				craterareaofeffect = 0,
				craterboost = 0,
				cratermult = 0,
				edgeeffectiveness = 0.15,
				energypershot = 100, -- the engine's own floor; the gadget draws the real cost from the bank
				explosiongenerator = "custom:laserhit-medium-red",
				firestarter = 90,
				impactonly = 1,
				impulsefactor = 0,
				laserflaresize = 11,
				leadlimit = 0,
				name = "Halberd Heat Ray",
				noselfdamage = true,
				range = 330,
				reloadtime = 1.2,
				rgbcolor = "1 0.45 0.05",
				rgbcolor2 = "1 0.95 0.55",
				soundhitdry = "",
				soundhitwet = "sizzle",
				soundstart = "heliosfire",
				soundtrigger = 1,
				thickness = 4.5,
				tolerance = 10000,
				turret = true,
				weapontype = "BeamLaser",
				weaponvelocity = 950,
				customparams = {
					va_ray_damage = "190", -- baseline per pulse; the gadget scales it
				},
				damage = {
					default = 190,
					vtol = 25,
				},
			},
		},
		weapons = {
			[1] = {
				badtargetcategory = "VTOL",
				def = "VA_HEAT_RAY",
				onlytargetcategory = "NOTSUB",
			},
		},
	},
}
