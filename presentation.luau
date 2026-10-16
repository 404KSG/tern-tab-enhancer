-- The tab structure, palette data and typography stay native to Tern.
local M = {}
M.colors = {working = "#3B82F6", waiting = "#F59E0B", done = "#22C55E"}
M.base = [[
#sidebar .tn-vt .nav-items .nav-row,
#tabbar .tt {position:relative;padding-right:30px;}
#sidebar .tn-vt .nav-items .nav-row > .tn-tc,
#tabbar .tt > .tn-tc {display:none;}
#sidebar .tn-dk-c[data-st]::after,
#tabbar .tn-dk-c[data-st]::after {display:none;}
/* Once cards are static, their old inset gloss would cover the entire row. */
#sidebar .tn-dk-c[data-st='working']::before,
#tabbar .tn-dk-c[data-st='working']::before {display:none;}
/* Tern 0.9 has no parent :has() selector. Keep the icon deck overlapped,
   but let its front card's status pseudo-element anchor to the tab row. */
#sidebar .tn-vt .nav-items .nav-row .tn-dk,
#tabbar .tt > .tn-dk {
  position:static;display:grid;grid-template-columns:18px;grid-template-rows:18px;
  width:18px;height:18px;transform:none;filter:none;z-index:auto;
}
#tabbar .tt .fc {display:none;}
#sidebar .tn-vt .nav-items .nav-row .tn-dk-c,
#tabbar .tt .tn-dk-c {
  position:static;display:grid;grid-column:1;grid-row:1;align-self:start;justify-self:start;
  width:13.32px;height:13.32px;margin:2.34px 0 0 2.34px;
  transform:none;filter:none;animation:none;z-index:auto;
}
#sidebar .tn-dk.n2.row .tn-dk-c.d0,
#tabbar .tn-dk.n2.row .tn-dk-c.d0 {margin-left:0.54px;}
#sidebar .tn-dk.n3.row .tn-dk-c.d0,
#tabbar .tn-dk.n3.row .tn-dk-c.d0 {margin-left:0;}
#sidebar .tn-dk.row .tn-dk-c.d1,
#tabbar .tn-dk.row .tn-dk-c.d1 {width:11.45px;height:11.45px;margin:3.28px 0 0 5.34px;}
#sidebar .tn-dk.row .tn-dk-c.d2,
#tabbar .tn-dk.row .tn-dk-c.d2 {width:9.59px;height:9.59px;margin:4.21px 0 0 9.05px;}
#sidebar .tn-dk.col .tn-dk-c.d1,
#tabbar .tn-dk.col .tn-dk-c.d1 {width:11.45px;height:11.45px;margin:0.9px 0 0 3.28px;}
#sidebar .tn-dk.col .tn-dk-c.d2,
#tabbar .tn-dk.col .tn-dk-c.d2 {width:9.59px;height:9.59px;margin:0 0 0 4.21px;}
#sidebar .tn-vt .nav-items .nav-row[data-tc],
#tabbar .tt[data-tc] {
  background-color:rgb(from var(--tc) r g b / 9%);
  color:var(--tc);
}
#sidebar .tn-vt .nav-items .nav-row[data-tc]:hover,
#tabbar .tt[data-tc]:hover {
  background-color:rgb(from var(--tc) r g b / 19%);
  box-shadow:inset 0 0 0 1px rgb(from var(--tc) r g b / 18%);
}
#sidebar .tn-vt .nav-items .nav-row.on[data-tc],
#tabbar .tt.on[data-tc] {
  background-color:rgb(from var(--tc) r g b / 25%);
  box-shadow:inset 0 0 0 1px rgb(from var(--tc) r g b / 32%);
}
#sidebar .tn-vt .nav-items .nav-row.on[data-tc]:hover,
#tabbar .tt.on[data-tc]:hover {background-color:rgb(from var(--tc) r g b / 30%);}
#tabbar .tb-fill[data-tc] {background:transparent;}
/* Colored working titles keep native shimmer timing, but not its gray/white ink. */
#sidebar .tn-vt .nav-items .nav-row.working[data-tc] > .lbl,
#tabbar .tt.working[data-tc] .nm {
  background-image:linear-gradient(90deg,
    rgb(from var(--tc) r g b / 80%) 0%,
    rgb(from var(--tc) r g b / 80%) 35%,
    var(--tc) 50%,
    rgb(from var(--tc) r g b / 80%) 65%,
    rgb(from var(--tc) r g b / 80%) 100%);
}
#sidebar .tn-vt .nav-items .nav-row .tn-dk-c::after,
#tabbar .tt .tn-dk-c::after {
  content:"";display:none;position:absolute;right:10px;left:auto;top:50%;bottom:auto;
  margin-top:-2.5px;width:5px;height:5px;
  box-sizing:border-box;border-radius:50%;border:0;box-shadow:none;
  color:#ffffff;font-family:var(--sans);font-size:9px;font-weight:700;
  line-height:14px;text-align:center;pointer-events:none;z-index:2;
}
@keyframes tteWorking {
  0%,100% {opacity:1;}
  50% {opacity:0.4;}
}
@media (prefers-reduced-motion: reduce) {
  #sidebar .tn-vt .nav-items .nav-row .tn-dk-c::after,
  #tabbar .tt .tn-dk-c::after {animation:none !important;opacity:1 !important;}
}
]]

local function selectors(tab)
    local result = {}
    for _, id in ipairs(tab.selectors) do
        -- Only exact decimal pane IDs from the native roster are interpolated.
        if string.match(id, "^%d+$") then
            local match = '.tn-dk-c.d0:not(.out)[data-pane="' .. id .. '"]::after'
            table.insert(result, "#sidebar .tn-vt .nav-items .nav-row " .. match)
            table.insert(result, "#tabbar .tt " .. match)
        end
    end
    return table.concat(result, ",\n")
end

function M.render(tabs)
    local rules = {M.base}
    for _, tab in ipairs(tabs) do
        local color = M.colors[tab.state]
        local selector = selectors(tab)
        if color and selector ~= "" then
            local paint
            if tab.label ~= "" then
                paint = 'content:"' .. tab.label .. '";width:14px;height:14px;right:5.5px;margin-top:-7px;background:' .. color .. ';animation:none;opacity:1;'
            elseif tab.state == "waiting" then
                paint = 'content:"";background:transparent;border:1px solid ' .. color .. ';animation:none;opacity:1;'
            else
                paint = 'content:"";background:' .. color .. ';'
                paint ..= if tab.state == "working" then 'animation:tteWorking 1s steps(1,end) infinite;' else 'animation:none;opacity:1;'
            end
            table.insert(rules, selector .. '{display:block;' .. paint .. '}')
        end
    end
    return table.concat(rules, "\n")
end
return M
