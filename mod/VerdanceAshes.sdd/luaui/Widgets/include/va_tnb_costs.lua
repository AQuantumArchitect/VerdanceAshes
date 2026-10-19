-- Stub only: real modules live in luaui/Include/.
-- BAR recursively scans Widgets/ and errors on library files without GetInfo.
function widget:GetInfo()
  return {
    name = "VA Include Stub",
    desc = "Not a widget — library moved to luaui/Include",
    author = "Verdance",
    date = "2026-09-09",
    license = "GPL v2 or later",
    layer = 0,
    enabled = false,
  }
end
