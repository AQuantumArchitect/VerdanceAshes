# BAR RML Starter Reference Notes

Reference ingested from:

```text
https://github.com/mupersega/Beyond-All-Reason/tree/bar-ui-2.0/luaui/RmlWidgets/rml_starter
```

Raw files are stored at:

```text
docs/references/bar-ui-2.0/rml_starter/
```

## File Pattern

RML widgets are organized as a three-file folder:

```text
luaui/RmlWidgets/<widget_name>/<widget_name>.lua
luaui/RmlWidgets/<widget_name>/<widget_name>.rml
luaui/RmlWidgets/<widget_name>/<widget_name>.rcss
```

The starter generator is Bash-only. On Windows, use Git Bash or WSL rather than PowerShell.

## Lua Lifecycle Pattern

The RML Lua widget:

- exits early if `RmlUi` is unavailable
- includes `luaui/Include/rml_utilities/utils.lua`
- defines stable `WIDGET_ID`, `MODEL_NAME`, and `RML_PATH`
- creates a fresh model table on every initialize
- calls `utils.initializeRmlWidget(...)` in `widget:Initialize()`
- calls `utils.shutdownRmlWidget(...)` in `widget:Shutdown()`
- keeps `document` and `dm_handle` module-local

Minimal generated widgets should avoid per-frame `Update()` unless needed.

## Data Model Rule

The central rule is "the model is king."

Use model fields and model functions as the view/controller boundary. In RML, use:

- `{{field}}`
- `data-if`
- `data-visible`
- `data-for`
- `data-event-click`
- `data-event-mouseover`
- `data-attr-class`
- `data-class-*`
- `data-attr-style`

Avoid directly driving UI through `GetElementById`, `QuerySelector`, `SetClass`, `SetAttribute`, `inner_rml`, or `AppendChild`, except for documented exceptions such as SVG injection or rare data-binding limitations.

## Style Pattern

RML imports common styles before widget-local RCSS:

```text
../styles.rcss
../rml-utility-classes.rcss
../palette-standard-global.rcss
../components.rcss
../themes/theme-base.rcss
../themes/theme-armada.rcss
../themes/theme-cortex.rcss
../themes/theme-legion.rcss
<widget>.rcss
```

Generated widgets use utility classes by default and `ccg.*` class groups for repeated heavy components like panels and buttons.

The generator explicitly prefers compact HUD boxes sized to content.

## Layout Cautions

The generator warns against nested `flex-direction: column` layouts for performance. Prefer block layout for dense HUD widgets unless row layout is clearly needed.

Use hard-coded `dp` dimensions for fixed widget frames. Avoid percentage sizing for primary widget width/height.

Frame radius should come from the style-mode axis. Avoid adding rounded body classes casually, and keep small interior elements square.

## SVG Notes

RML SVG elements can receive generated SVG strings through:

```lua
el:SetAttribute("src", svgString)
```

Raw SVG via `inner_rml` does not render. Absolute VFS paths do not resolve. SVG elements are opaque, and `clip-path` is unavailable.

## Verdance Implication

RML is useful later for a tactical overlay or local operator panel, but it is not required for v1 telemetry. The v1 priority remains LuaRules telemetry export plus headless validation.

When the overlay becomes relevant, use a small RML widget that reads already-exported telemetry or receives LuaRules messages. Do not put tactical interpretation inside the RML layer.
