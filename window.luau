-- Tern's load hook has 50ms. Wait for a usable window, then give each
-- module its own callback budget; no metadata read happens during load.
local started, fallback = false, nil
local function bootstrap()
    if started then return end
    started = true
    if fallback then fallback:cancel(); fallback = nil end
    tern.timer(0, function()
        local Model = require("./model")
        tern.timer(0, function()
            local Presentation = require("./presentation")
            tern.timer(0, function()
                local Runtime = require("./runtime")
                tern.timer(0, function()
                    Runtime.start(tern, Model, Presentation)
                end)
            end)
        end)
    end)
end
local function retry(cx)
    fallback = nil
    if started then return end
    if cx and cx.session:focused() then
        bootstrap()
    else
        fallback = tern.timer(100, retry)
    end
end
tern.on("window_start", bootstrap)
tern.on("pane_created", bootstrap)
if not started then fallback = tern.timer(100, retry) end
