function widget:GetInfo()
    return {
        name      = "Campaign Overmind Visualizer",
        desc      = "Renders the Verdance Campaign Canonical Interface Packet using Chili.",
        author    = "Antigravity",
        date      = "2026",
        license   = "GNU GPL, v2 or later",
        layer     = 0,
        -- Not the play path (Ash Console = objectives HUD). Off by default.
        enabled   = false,
        handler   = true
    }
end

local Chili
local Window
local ScrollPanel
local StackPanel
local Label
local Progressbar
local TextBox

local packet = nil
local updateRequired = false
local mainWin

function widget:Initialize()
    Spring.Echo("[Verdance Overmind] Initializing Widget...")
    if not WG.Chili then
        Spring.Echo("[Verdance Overmind ERROR] WG.Chili is not loaded yet! Widget cannot start.")
        widgetHandler:RemoveWidget(widget)
        return
    end
    
    Spring.Echo("[Verdance Overmind] Chili found, building UI...")
    Chili = WG.Chili
    Window = Chili.Window
    ScrollPanel = Chili.ScrollPanel
    StackPanel = Chili.StackPanel
    Label = Chili.Label
    Progressbar = Chili.Progressbar
    TextBox = Chili.TextBox

    -- Bind the UI receiver to the global WG table so the gadget can call it
    WG.VerdanceTelemetry = function(jsonStr)
        -- Basic custom schema parser to avoid heavy JSON libraries
        local parsed = { global = { hydrology = {} }, nodes = {}, entanglements = {}, factoids = {} }
        
        local sat = jsonStr:match('"saturation":([%d%.]+)')
        if sat then parsed.global.hydrology.saturation = tonumber(sat) end
        
        for name, dens, hc in jsonStr:gmatch('{"id":%d+,"name":"([^"]+)","type":"[^"]+","density":([%d%.]+),"hydroCoupling":([%d%.]+)}') do
            table.insert(parsed.nodes, {name=name, density=tonumber(dens), hydroCoupling=tonumber(hc)})
        end
        for n1, n2, c in jsonStr:gmatch('{"names":%["([^"]+)","([^"]+)"%],"coupling":([%d%.]+)}') do
            table.insert(parsed.entanglements, {names={n1, n2}, coupling=tonumber(c)})
        end
        for t, msg in jsonStr:gmatch('{"type":"([^"]+)","zoneId":%d+,"message":"([^"]+)"}') do
            table.insert(parsed.factoids, {type=t, message=msg})
        end

        packet = parsed
        updateRequired = true
    end

    SetupWindow()
end

function widget:Shutdown()
    WG.VerdanceTelemetry = nil
    if mainWin then mainWin:Dispose() end
end

-- Called by Script.LuaUI from the Unsynced Gadget
function widget:VerdanceTelemetry(jsonStr)
    if WG.VerdanceTelemetry then WG.VerdanceTelemetry(jsonStr) end
end

function SetupWindow()
    mainWin = Window:New{
        parent = Chili.Screen0,
        name   = "overmind_main",
        color = {0, 0, 0, 0.9},
        x = "20%", y = "20%",
        width = 450, height = 650,
        draggable = true, resizable = true,
        children = {
            ScrollPanel:New{
                x = 0, y = 0, width = "100%", height = "100%",
                name = "main_scroll", children = {}
            }
        }
    }
end

function widget:Update()
    if updateRequired and packet then
        updateRequired = false
        RedrawUI()
    end
end

function RedrawUI()
    local scroll = mainWin:GetChildByName("main_scroll")
    scroll:ClearChildren()

    local stack = StackPanel:New{
        parent = scroll, width = "100%", height = "100%",
        padding = {10,10,10,10}, itemMargin = {0, 10, 0, 10}, autoArrangeV = true,
    }

    local sat = (packet.global.hydrology.saturation or 0) * 100
    Label:New{ parent = stack, width = "100%", height = 30, caption = "GLOBAL HYDROLOGY: " .. string.format("%.1f", sat) .. "%", font = {size = 20, color = {0.43, 0.57, 0.69, 1}} }

    Label:New{ parent = stack, width = "100%", height = 20, caption = "TERRITORY GRAPH", font = {size = 14, color = {0.92, 0.86, 0.72, 1}} }
    for i, node in ipairs(packet.nodes) do
        local ns = StackPanel:New{ parent = stack, width = "100%", height = 30, orientation = "horizontal", autoArrangeH = true, itemMargin = {10,0,10,0} }
        Label:New{ parent = ns, width = 100, height = "100%", caption = node.name, font = {size = 12} }
        local dCol = {0.84, 0.53, 0.29, 1}
        if node.density > 0.8 then dCol = {0.74, 0.39, 0.31, 1} end
        Progressbar:New{ parent = ns, width = 120, height = 15, value = node.density * 100, max = 100, color = dCol }
        Progressbar:New{ parent = ns, width = 60, height = 10, value = node.hydroCoupling * 100, max = 100, color = {0.43, 0.57, 0.69, 1} }
    end

    Label:New{ parent = stack, width = "100%", height = 20, caption = "ACTIVE ENTANGLEMENTS", font = {size = 14, color = {0.92, 0.86, 0.72, 1}} }
    for i, ent in ipairs(packet.entanglements) do
        Label:New{ parent = stack, width = "100%", height = 20, caption = ent.names[1] .. " <--> " .. ent.names[2] .. " (Coupling: " .. string.format("%.1f%%", ent.coupling*100) .. ")", font = {size = 12, color = {0.84, 0.53, 0.29, 1}} }
    end

    Label:New{ parent = stack, width = "100%", height = 20, caption = "OVERMIND TELEMETRY", font = {size = 14, color = {0.92, 0.86, 0.72, 1}} }
    for i, fact in ipairs(packet.factoids) do
        local fCol = {0.74, 0.39, 0.31, 1}
        if fact.type == "HAZARD" then fCol = {0.43, 0.57, 0.69, 1} end
        TextBox:New{ parent = stack, width = "100%", height = 40, text = "[" .. fact.type .. "] " .. fact.message, font = {size = 12, color = fCol} }
    end
end
