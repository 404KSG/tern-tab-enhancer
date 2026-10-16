local Model = require("./model")
local Presentation = require("./presentation")
local passed, names = 0, {}
local function test(name, fn)
    local ok, err = pcall(fn)
    assert(ok, name .. ": " .. tostring(err))
    passed += 1
    table.insert(names, name)
end
local function eq(actual, expected)
    assert(actual == expected, tostring(actual) .. " ~= " .. tostring(expected))
end
local function pane(id, tab, focused, alert)
    return {pane = id, tab = tab or 10, kind = "agent", focused = focused == true, alert = alert == true}
end
local function agent(id, state) return {pane = id, state = state} end
local function update(model, panes, agents, aliases)
    return Model.update(model, panes, agents, aliases)[1]
end

test("initial idle has no indicator", function()
    eq(update(Model.new(), {pane(1)}, {agent(1, "idle")}).state, "idle")
end)
test("working is blue without count", function()
    local tab = update(Model.new(), {pane(1)}, {agent(1, "working")})
    eq(tab.state, "working"); eq(tab.label, "")
    eq(Presentation.colors.working, "#3B82F6")
end)
test("waiting wins over working and done", function()
    local m = Model.new(); Model.finished(m, 3, "done", nil)
    local tab = update(m, {pane(1),pane(2),pane(3)}, {agent(1,"working"),agent(2,"waiting_input"),agent(3,"idle")})
    eq(tab.state, "waiting"); eq(tab.label, "")
    eq(Presentation.colors.waiting, "#F59E0B")
end)
test("working wins over unread completion like tty7", function()
    local m=Model.new(); Model.finished(m,2,"done",nil)
    local tab=update(m,{pane(1),pane(2)},{agent(1,"working"),agent(2,"idle")})
    eq(tab.state,"working"); eq(tab.unread,1); eq(tab.count,0)
end)
test("unseen completed pane shows one", function()
    local m=Model.new(); Model.finished(m,1,"done",nil)
    local tab=update(m,{pane(1)},{agent(1,"idle")})
    eq(tab.state,"done");eq(tab.label,"1")
end)
test("focused completion is read but remains done", function()
    local m=Model.new();Model.finished(m,1,"done",1)
    local tab=update(m,{pane(1,10,true)},{agent(1,"idle")})
    eq(tab.state,"done");eq(tab.label,"")
end)
test("four panes count past native three-icon stack", function()
    local m=Model.new();local ps,ags={},{}
    for id=1,4 do Model.finished(m,id,"done",nil);table.insert(ps,pane(id));table.insert(ags,agent(id,"idle")) end
    eq(update(m,ps,ags).label,"4")
    Model.focus(m,2)
    eq(update(m,ps,ags).label,"3")
    Model.focus(m,4)
    eq(update(m,ps,ags).label,"2")
end)
test("many messages from one pane count once", function()
    local m=Model.new()
    for _=1,7 do Model.finished(m,1,"done",nil) end
    eq(update(m,{pane(1)},{agent(1,"idle")}).label,"1")
end)
test("unread count capped at nine like tty7", function()
    local m=Model.new();local ps,ags={},{}
    for id=1,12 do Model.finished(m,id,"done",nil);table.insert(ps,pane(id));table.insert(ags,agent(id,"idle")) end
    local tab=update(m,ps,ags);eq(tab.count,12);eq(tab.label,"9")
end)
test("reading another pane does not acknowledge siblings", function()
    local m=Model.new();Model.finished(m,1,"done",nil);Model.finished(m,2,"done",nil);Model.focus(m,1)
    eq(update(m,{pane(1),pane(2)},{agent(1,"idle"),agent(2,"idle")}).count,1)
end)
test("next turn clears old read marker", function()
    local m=Model.new();Model.finished(m,1,"done",1)
    update(m,{pane(1)},{agent(1,"working")});Model.finished(m,1,"done",nil)
    eq(update(m,{pane(1)},{agent(1,"idle")}).count,1)
end)
test("native attention imported on plugin first load", function()
    eq(update(Model.new(),{pane(1,10,false,true)},{agent(1,"idle")}).count,1)
end)
test("viewed completion survives reload despite native alert", function()
    local m=Model.new();Model.finished(m,1,"done",1)
    local restored=Model.new(m.records)
    eq(update(restored,{pane(1,10,false,true)},{agent(1,"idle")}).count,0)
end)
test("closed pane is pruned", function()
    local m=Model.new();Model.finished(m,1,"done",nil)
    eq(#Model.update(m,{},{}),0);eq(next(m.records),nil)
end)
test("move recomputes tab and preserves unread identity", function()
    local m=Model.new();Model.finished(m,1,"done",nil)
    eq(update(m,{pane(1,20)},{agent(1,"idle")}).id,20)
    eq(update(m,{pane(1,30)},{agent(1,"idle")}).count,1)
end)
test("ordinary shell is never guessed to be a working agent", function()
    local m=Model.new()
    eq(#Model.update(m,{{pane=1,tab=10,kind="terminal",busy=true}},{}),0)
end)
test("all pane selectors retain badge after shell focus", function()
    local m=Model.new();Model.finished(m,1,"done",nil)
    local tab=update(m,{pane(1),{pane=2,tab=10,kind="terminal"}},{agent(1,"idle")},{["1"]="394471271301128",["2"]="394471271301130"})
    eq(#tab.selectors,2)
    local css=Presentation.render({tab})
    assert(string.find(css,'data-pane="394471271301130"',1,true))
end)
test("failed turn uses done semantics without claiming success", function()
    local m=Model.new();Model.finished(m,1,"failed",nil)
    eq(update(m,{pane(1)},{agent(1,"idle")}).state,"done")
end)
test("waiting is hollow and no purple icon-dot relocation", function()
    local css=Presentation.render({{state="waiting",label="",selectors={"1"}}})
    assert(string.find(css,"border:1px solid #F59E0B",1,true))
    assert(string.find(css,"#sidebar .tn-dk-c[data-st]::after",1,true))
    assert(not string.find(css,"color_tab",1,true))
end)
test("stable native selectors survive duplicate names and tab reordering", function()
    local css=Presentation.render({{state="done",label="2",selectors={"5","6"}}})
    assert(string.find(css,'content:"2"',1,true))
    assert(not string.find(css,"nth-child",1,true))
    assert(not string.find(css,"title=",1,true))
end)

test("working-title shimmer keeps the manually selected tab hue", function()
    local css=Presentation.base
    assert(string.find(css,".nav-row.working[data-tc] > .lbl",1,true),"vertical working title has no hue override")
    assert(string.find(css,".tt.working[data-tc] .nm",1,true),"horizontal working title has no hue override")
    local block=string.match(css,"/\* Colored working titles.-\*/%s*(.-)\n}")
    assert(block and string.find(block,"background-image:linear-gradient",1,true))
    assert(string.find(block,"var(--tc) 50%",1,true))
    assert(not string.find(block,"var(--t1)",1,true),"native white highlight leaked into manual hue")
    assert(not string.find(block,"animation:",1,true),"title animation timing was changed")
end)

-- Exercise the actual window module against a native-shaped API mock.
local function runtime(start_window)
    local time, timers, handlers, commands, css_calls, writes, reads, requires = 0, {}, {}, {}, {}, 0, 0, 0
    local storage = {}
    local ps={pane(1)};local ags={agent(1,"working")}
    local cx={session={},agents={}}
    function cx.session:panes() return ps end
    function cx.session:pane(id) for _,p in ipairs(ps) do if Model.key(p.pane)==id then return p end end end
    function cx.session:focused() for _,p in ipairs(ps) do if p.focused then return p.pane end end return nil end
    function cx.agents:list() return ags end
    local function clone(value)
        if type(value)~="table" then return value end
        local result={};for k,v in pairs(value) do result[k]=clone(v) end;return result
    end
    local api={kv={},json={null={}},on=function(name,fn) handlers[name]=fn end,
        command=function(def) commands[def.id]=def.run end,
        now=function() return time end,
        css=function(name,source) table.insert(css_calls,source) end,
        on_require=function() requires+=1 end,
    }
    function api.kv.get(k) reads+=1;return clone(storage[k]) end
    function api.kv.set(k,v) storage[k]=clone(v);writes+=1 end
    function api.timer(ms,fn)
        local timer={ms=ms,fn=fn,cancelled=false}
        function timer:cancel() self.cancelled=true end
        table.insert(timers,timer);return timer
    end
    load_window_plugin(api)
    if start_window ~= false then handlers.window_start(cx) end
    local result={ctx=cx,commands=commands,handlers=handlers,css=css_calls}
    function result.tick()
        for _,timer in ipairs(timers) do
            if not timer.cancelled and not timer.fired then
                timer.fired=true;time+=timer.ms;timer.fn(cx);return
            end
        end
        error("No pending refresh")
    end
    function result.pending()
        local count=0;for _,t in ipairs(timers) do if not t.cancelled and not t.fired then count+=1 end end;return count
    end
    function result.writes() return writes end
    function result.reads() return reads end
    function result.requires() return requires end
    function result.ready()
        for _=1,8 do
            if #css_calls>0 then return end
            result.tick()
        end
        error("Bootstrap did not finish")
    end
    function result.set(panes,agents) ps,ags=panes,agents end
    return result
end

test("load hook defers module IO and KV reads to separate callbacks",function()
    local r=runtime();eq(r.requires(),0);eq(r.reads(),0);eq(#r.css,0);eq(r.pending(),1)
    r.ready();eq(r.requires(),3);eq(#r.css,1)
end)

test("cold bootstrap waits for the window lifecycle",function()
    local r=runtime(false);r.tick();eq(r.requires(),0);eq(r.reads(),0)
    r.handlers.window_start(r.ctx);r.ready();eq(r.requires(),3);eq(#r.css,1)
    r.handlers.window_start(r.ctx);eq(r.requires(),3)
end)

test("thirty steady-state polls do not replace stylesheet", function()
    local r=runtime();r.ready();local applies=#r.css;local writes=r.writes()
    for _=1,30 do r.tick() end
    eq(#r.css,applies);eq(r.writes(),writes)
end)
test("title storms coalesce into one scheduled refresh", function()
    local r=runtime();r.ready()
    for _=1,500 do r.handlers.title({pane=1,title="unchanged"},r.ctx) end
    eq(r.pending(),1);r.tick();eq(r.pending(),1);eq(#r.css,1)
end)
test("pause removes all plugin styling and resume restores it", function()
    local r=runtime();r.ready();r.commands.pause(r.ctx);eq(r.css[#r.css],"")
    for _=1,5 do r.tick() end
    eq(r.css[#r.css],"");r.commands.resume(r.ctx)
    assert(string.find(r.css[#r.css],"#3B82F6",1,true))
end)
test("completion and focus events refresh native count", function()
    local r=runtime();r.ready();r.set({pane(1)},{agent(1,"idle")})
    r.handlers.agent_finished({pane=1,result="done"},r.ctx);r.tick()
    assert(string.find(r.css[#r.css],'content:"1"',1,true))
    r.handlers.focus({pane=1},r.ctx);r.tick()
    assert(not string.find(r.css[#r.css],'content:"1"',1,true))
end)
test("ordinary terminal Pi bridge supplies precise waiting", function()
    local ps={{pane=1,tab=10,kind="terminal",busy=true}}
    local sources=Model.with_bridges(ps,{}, {["1"]="394471271301128"}, {["394471271301128"]={state="waiting",generation="abc:1"}})
    eq(#sources,1);eq(update(Model.new(),ps,sources).state,"waiting")
end)
test("native and bridge records for one pane never double count", function()
    local ps={pane(1)}
    local sources=Model.with_bridges(ps,{agent(1,"working")},{},{["1"]={state="done",generation="abc:1"}})
    eq(#sources,1);eq(update(Model.new(),ps,sources).count,1)
end)
test("bridge generation rearms exactly one unread result", function()
    local m=Model.new();local ps={pane(1)}
    local function report(phase,generation)
        return update(m,ps,Model.with_bridges(ps,{}, {}, {["1"]={state=phase,generation=generation}}))
    end
    eq(report("done","abc:1").count,1);Model.focus(m,1)
    eq(report("done","abc:1").count,0)
    eq(report("done","abc:2").count,1)
    eq(report("idle","new-process:0").state,"idle")
end)
test("idle dialog cannot rearm a viewed completion", function()
    local m=Model.new();local ps={pane(1)}
    local function report(phase)
        return update(m,ps,Model.with_bridges(ps,{}, {}, {["1"]={state=phase,generation="abc:1"}}))
    end
    report("done");Model.focus(m,1);eq(report("waiting").state,"waiting")
    eq(report("done").count,0)
    Model.finished(m,1,"done",nil)
    eq(report("done").count,0)
end)

local function host_runtime()
    local clock, timers, storage, writes = 0, {}, {}, 0
    local report={schema=1,pane="1",state="working",generation="abc:1",sequence=1}
    local api={plugin={data="/plugin"},kv={},fs={},json={},pane={},on=function() end,now=function() return clock end}
    function api.pane.list() return {{pane=1}} end
    function api.fs.exists() return report~=nil end
    function api.fs.read(_,limit) eq(limit,4096);return "report" end
    function api.json.decode() return report end
    function api.kv.set(k,v) storage[k]=v;writes+=1 end
    function api.timer(ms,fn) table.insert(timers,{ms=ms,fn=fn});return {cancel=function() end} end
    load_host_plugin(api)
    local result={storage=storage}
    function result.tick()
        local timer=table.remove(timers,1);clock+=timer.ms;timer.fn()
    end
    function result.report(value) report=value end
    function result.value() return report end
    function result.writes() return writes end
    return result
end

test("host bridge heartbeat does not rewrite unchanged status KV",function()
    local h=host_runtime();eq(h.storage["bridge-states"]["1"].state,"working")
    local writes=h.writes()
    for _=1,20 do h.value().sequence+=1;h.tick() end
    eq(h.writes(),writes)
end)
test("host expires a stopped heartbeat rather than retaining working forever",function()
    local h=host_runtime()
    for _=1,31 do h.tick() end
    eq(next(h.storage["bridge-states"]),nil)
    h.value().sequence+=1;h.tick();eq(h.storage["bridge-states"]["1"].state,"working")
end)
test("host rejects malformed bridge records",function()
    local h=host_runtime();h.report({schema=1,pane="OTHER",state="working",generation="abc:1",sequence=2});h.tick()
    eq(next(h.storage["bridge-states"]),nil)
end)
return passed, names
