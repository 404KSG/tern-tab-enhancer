local root = tern.getenv("TERN_TAB_TEST_DIR")
local function snapshot(cx)
    local started = tern.now()
    local source = cx.agents:list()
    local agents = {}
    for _, agent in ipairs(source) do
        table.insert(agents, {pane = agent.pane, command = agent.command, state = agent.state})
    end
    tern.fs.write(root .. "/snapshot.json", tern.json.encode({
        agents = tern.json.array(agents), agents_ms = tern.now() - started,
        tabs = tern.json.array(cx.session:tabs()), panes = tern.json.array(cx.session:panes()),
        focused = cx.session:focused(),
    }))
end
tern.command({id = "snapshot", title = "Test: snapshot", run = snapshot})
tern.command({id = "drive", title = "Test: drive", run = function(cx)
    local request = tern.json.decode(tern.fs.read(root .. "/drive.json"))
    if request.op == "settings" then cx.settings:set_many(request.values)
    elseif request.op == "new" then cx.layout:new_tab({command = request.command, cwd = root})
    elseif request.op == "split" then cx.layout:split(request.pane, "right", {command = request.command, cwd = root})
    elseif request.op == "focus" then cx.layout:focus(request.pane)
    elseif request.op == "color" then cx.layout:color_tab(request.tab, request.color)
    elseif request.op == "move" then cx.layout:move_to_tab(request.pane, request.tab)
    elseif request.op == "close" then cx.layout:close(request.pane)
    elseif request.op == "send" then cx:run(request.pane, request.text)
    else error("Unknown test operation") end
    snapshot(cx)
end})
