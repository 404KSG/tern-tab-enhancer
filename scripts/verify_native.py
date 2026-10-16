#!/usr/bin/env python3
"""Native Tern acceptance with owned processes, offline OSC fixtures and pixel checks."""
from __future__ import annotations
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import shlex
import subprocess
import time
from PIL import Image
from package_plugin import package_files, stage_package

PROJECT = Path(__file__).resolve().parents[1]
TERN = '/Applications/Tern.app/Contents/MacOS/tern'
RUNTIME = package_files(PROJECT, runtime_only=True)
parser = argparse.ArgumentParser()
parser.add_argument('--out', type=Path)
parser.add_argument('--pi-dialog-rounds', type=int, default=1)
args = parser.parse_args()
if args.pi_dialog_rounds < 1:
    parser.error('至少验证一次 Pi 提问恢复')
root = (args.out or PROJECT/'artifacts/native'/datetime.now().strftime('%Y%m%d-%H%M%S')).resolve()
root.mkdir(parents=True, exist_ok=True)
config = root/'config'
plugins = config/'plugins'
plugins.mkdir(parents=True, exist_ok=True)
control = root/'control.sock'
daemon = root/'daemon.sock'
env = {k:v for k,v in os.environ.items() if not k.startswith(('TERN_','PI_','OMP_','ANTHROPIC_','OPENAI_','GOOGLE_','GEMINI_','AWS_','AZURE_','NODE_OPTIONS'))}
env.update(TERN_CONFIG_DIR=str(config), TERN_DAEMON_SOCKET=str(daemon), TERN_TAB_TEST_DIR=str(root), STENCIL_LOG_DIR=str(root/'logs'), STENCIL_LOG='warn,tern::plugin=debug')
summary = {'started':datetime.now().astimezone().isoformat(), 'root':str(root), 'cases':[], 'processes':[], 'result':'running'}
owned = []


def save():
    (root/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))


def command(*argv):
    result = subprocess.run([TERN,*map(str,argv)], capture_output=True, text=True, env=env, cwd=root, timeout=20)
    if result.returncode:
        raise RuntimeError(f'{argv}: {result.stderr or result.stdout}')
    return result.stdout


def ctl(*argv):
    data = json.loads(command('ctl','--control',control,*argv))
    if not data.get('ok'):
        raise RuntimeError(data)
    return data


def until(fn, timeout=8, label='native condition'):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        # A background macOS window may render sparsely. Pump its own control
        # endpoint so this acceptance loop waits on actual GUI frames.
        if control.exists():
            try:ctl('stats')
            except (RuntimeError,subprocess.SubprocessError):pass
        result = fn()
        if result:
            return result
        time.sleep(.06)
    raise TimeoutError(label+' did not settle')


def snapshot(operation=None):
    path = root/'snapshot.json'
    path.unlink(missing_ok=True)
    if operation:
        (root/'drive.json').write_text(json.dumps(operation))
        ctl('plugins','run','plugin.tab-enhancer-observer.drive')
    else:
        ctl('plugins','run','plugin.tab-enhancer-observer.snapshot')
    until(path.exists)
    return json.loads(path.read_text())


def send(pane, text):
    snapshot({'op':'send','pane':pane,'text':text+'\r'})


def focus(pane):
    snapshot({'op':'focus','pane':pane})


def plugin_state():
    path = config/'plugin-data/tern-tab-enhancer/kv.json'
    return json.loads(path.read_text()) if path.exists() else {}


def records():
    state=plugin_state()
    return {key.removeprefix('state:'):value for key,value in state.items() if key.startswith('state:')}


def unread():
    return sum(r.get('done') and not r.get('read') for r in records().values())


def wait_status(state, count=None):
    def check():
        rs = records()
        return rs and any(r.get('status')==state for r in rs.values()) and (count is None or unread()==count)
    until(check)
    time.sleep(.12)


def row(selector=None):
    selector = selector or ('#sidebar .nav-items .nav-row[data-tc=red]' if ctl('state')['tab_orientation']=='vertical' else '#tabbar .tt[data-tc=red]')
    matches = [e for e in ctl('dump',selector)['elements'] if e.get('visible')]
    assert len(matches)==1, matches
    return matches[0]


def shot(name):
    return ctl('shot',name)


def pixels(name, state, numeric=False, expected_digit=None):
    result=shot(name)
    image=Image.open(result['png']).convert('RGB')
    x,y,w,h=row()['rect']
    box=(round(x+w-20),round(y+h/2-9),round(x+w-2),round(y+h/2+9))
    crop=image.crop(box)
    target={'working':(59,130,246),'waiting':(245,158,11),'done':(34,197,94)}[state]
    hits=0
    for rgb in crop.get_flattened_data():
        if max(abs(a-b) for a,b in zip(rgb,target))<35:
            hits+=1
        elif state=='working' and rgb[2]>rgb[1]+25 and rgb[1]>rgb[0]+15:
            hits+=1
    assert hits>=2, (name,state,hits)
    center_x=x+w-12.5-box[0]
    center_y=y+h/2-box[1]
    whites=sum(min(crop.getpixel((px,py)))>205 for py in range(crop.height) for px in range(crop.width)
               if (px+.5-center_x)**2+(py+.5-center_y)**2<25)
    if numeric:
        assert expected_digit is not None,'numeric cases require an independent expected digit'
        assert whites>=3, (name,'numeric pill has no visible glyph',whites)
        oracle=root/'digit-oracle.css'
        oracle.write_text('#sidebar .tn-dk-c.d0::after,#tabbar .tn-dk-c.d0::after{content:"'+str(expected_digit)+'" !important;}')
        try:
            ctl('css','tte-test-oracle',oracle)
            expected_image=Image.open(shot(name+'-oracle')['png']).convert('RGB').crop(box)
            def glyph(image):
                return tuple(min(image.getpixel((px,py)))>205 for py in range(image.height) for px in range(image.width)
                             if (px+.5-center_x)**2+(py+.5-center_y)**2<40)
            assert glyph(crop)==glyph(expected_image),(name,'wrong rendered digit',expected_digit)
        finally:
            ctl('css','tte-test-oracle')
    crop.resize((180,180)).save(root/f'{name}-badge.png')
    return {'png':result['png'],'colored_pixels':hits,'white_pixels':whites,'expected_digit':expected_digit,'digit_matches_oracle':numeric}


def title_box():
    selector='#sidebar .nav-items .nav-row[data-tc=red]>.lbl' if ctl('state')['tab_orientation']=='vertical' else '#tabbar .tt[data-tc=red] .nm'
    return [e['rect'] for e in ctl('dump',selector)['elements'] if e.get('visible')][0]


def case(name, fn):
    record={'name':name,'result':'running'}
    summary['cases'].append(record);save()
    try:
        record['evidence']=fn() or {}
        record['result']='passed'
        print(f'PASS {name}',flush=True)
    except Exception as error:
        record['result']='failed';record['error']=repr(error);save();raise
    save()


def launch(role, argv, ready):
    output=(root/f'{role}.out.log').open('ab')
    process=subprocess.Popen([TERN,*map(str,argv)],cwd=root,env=env,stdout=output,stderr=output,start_new_session=True)
    owned.append((process,output))
    summary['processes'].append({'role':role,'pid':process.pid})
    until(lambda:ready.exists() or process.poll() is not None)
    assert process.poll() is None,role
    save()


def stage():
    source=root/'package';source.mkdir(exist_ok=True)
    stage_package(source, runtime_only=True)
    command('plugin','install',source,'--json')
    command('plugin','install',PROJECT/'tests/fixtures/observer','--json')
    (config/'omp').mkdir(exist_ok=True)
    (config/'omp/state.json').write_text(json.dumps({'managed':False,'checked':0,'no_build':False,'offered':True}))
    launch('daemon',['daemon','--socket',daemon],daemon)
    launch('window',['--control',control,'--out',root/'shots',root],control)
    # The control socket precedes the cached account gate. Tern 0.9 can leave
    # the initial tab without a mounted pane (also reproduced with no plugins).
    # Create one explicitly after the gate settles, in this owned window only.
    until(lambda:ctl('state').get('gate',{}).get('phase')=='off',timeout=20,label='cached account gate')
    ctl('tab','new')
    until(lambda:len(ctl('state').get('panes',[]))>0,timeout=20,label='test pane registration')
    until(lambda:any(s['name']=='plugin:local:tern-tab-enhancer:tabs' and s['rules']>0 for s in ctl('css')['sheets']),
          timeout=15,label='window plugin bootstrap')
    ctl('ready')


try:
    stage()
    initial=snapshot();home=initial['focused']
    fixture='python3 '+str(PROJECT/'tests/fixtures/status_agent.py')
    snapshot({'op':'new','command':fixture})
    until(lambda:len(snapshot()['agents'])==1)
    first=snapshot()['agents'][0]['pane']
    for _ in range(3):snapshot({'op':'split','pane':first,'command':fixture})
    until(lambda:len(snapshot()['agents'])==4)
    state=snapshot();agents=[a['pane'] for a in state['agents']]
    target_tab=next(p['tab'] for p in state['panes'] if p['pane']==first)
    snapshot({'op':'settings','values':{'theme':'Dark','material':'Solid'}})
    snapshot({'op':'color','tab':target_tab,'color':'red'})
    ctl('tabs','vertical');focus(home)
    summary['versions']={'tern':command('--version').strip(),'protocol':'OSC 7501 as emitted by Pi 1.2.0','models_called':0}
    summary['native_agent_query_ms']=state['agents_ms']

    def working():
        for pane in agents:send(pane,'working')
        wait_status('working');return pixels('working-blue','working')
    case('working-blue',working)
    before_box=title_box()

    def working_title_hue():
        element=[e for e in ctl('dump','#sidebar .nav-items .nav-row[data-tc=red]>.lbl')['elements'] if e.get('visible')][0]
        x,y,w,h=element['rect']
        result=shot('working-title-hue')
        crop=Image.open(result['png']).convert('RGB').crop((round(x),round(y),round(x+w),round(y+h)))
        colored=sum(r>90 and r>g+35 and r>b+35 for r,g,b in crop.get_flattened_data())
        neutral=sum(min(r,g,b)>100 and max(r,g,b)-min(r,g,b)<15 for r,g,b in crop.get_flattened_data())
        assert colored>=25,(colored,neutral,'working title lost its manual hue')
        assert neutral==0,(colored,neutral,'working title still uses gray/white ink')
        animated=[p for p in ctl('stats').get('animating',{}).get('elements',[]) if '#sidebar' in p and '.working' in p and p.endswith('>span.lbl')]
        assert animated,'native working-title animation was disabled'
        return {'png':result['png'],'colored_text_pixels':colored,'gray_white_text_pixels':neutral,'native_title_animation':True}
    case('working-title-follows-manual-hue',working_title_hue)

    def waiting():
        send(agents[-1],'blocked');wait_status('waiting')
        result=pixels('waiting-amber','waiting')
        assert all(r.get('status') in ['working','waiting'] for r in records().values())
        return result
    case('waiting-over-working',waiting)

    def four_done():
        for pane in agents:send(pane,'done')
        wait_status('done',4)
        result=pixels('four-unread','done',True,4)
        assert title_box()==before_box,'badge changed title width'
        result['unread']=4
        return result
    case('four-panes-unread-count',four_done)

    def one_read():
        focus(agents[0]);until(lambda:unread()==3)
        time.sleep(.2);return {**pixels('three-unread','done',True,3),'unread':3}
    case('read-one-keeps-three-unread',one_read)

    def hover():
        focus(home);time.sleep(.2);ctl('hover',json.dumps('#sidebar .nav-head'))
        base=row()['backgroundColor']
        def hover_painted():
            ctl('hover',json.dumps('#sidebar .nav-items .nav-row[data-tc=red]'))
            return row()['backgroundColor'].endswith(', 0.19)')
        until(hover_painted,label='native hover paint')
        hovered=row()['backgroundColor']
        assert base!=hovered,(base,hovered)
        result={'base':base,'hover':hovered,'pointer':ctl('stats')['pointer'],'png':shot('colored-hover')['png']}
        ctl('hover',json.dumps('#sidebar .nav-head'))
        return result
    case('dia-hover-whole-row',hover)

    def selected():
        focus(first);time.sleep(.2)
        result={'background':row()['backgroundColor'],'png':shot('colored-selected')['png']}
        assert any(t.get('color')=='red' for t in snapshot()['tabs'])
        return result
    case('native-manual-color-preserved',selected)

    def stable():
        original=title_box()
        for _ in range(12):
            time.sleep(.08)
            assert title_box()==original
        return {'title_rect':original,'samples':12}
    case('stable-title-geometry',stable)

    def reload():
        count=unread();command('plugin','reload','--json');time.sleep(.6)
        assert unread()==count,(count,unread())
        assert any(t.get('color')=='red' for t in snapshot()['tabs'])
        return {**pixels('reload-unread','done',True,3),'unread':count}
    case('read-state-and-color-survive-reload',reload)

    def horizontal():
        ctl('tabs','horizontal');time.sleep(.25)
        return pixels('horizontal-counter','done',True,3)
    case('horizontal-counter',horizontal)

    def light():
        snapshot({'op':'settings','values':{'theme':'Light'}});time.sleep(.3)
        return pixels('light-counter','done',True,3)
    case('light-theme',light)

    def pause_resume():
        ctl('plugins','run','plugin.tern-tab-enhancer.pause');time.sleep(.2)
        sheets=[s for s in ctl('css')['sheets'] if 'tern-tab-enhancer' in s['name']]
        assert all(s['rules']==0 for s in sheets)
        assert any(t.get('color')=='red' for t in snapshot()['tabs'])
        ctl('plugins','run','plugin.tern-tab-enhancer.resume');time.sleep(.25)
        return pixels('resumed-counter','done',True,3)
    case('pause-resume',pause_resume)

    def all_read():
        for pane in agents:focus(pane)
        until(lambda:unread()==0);time.sleep(.25)
        return pixels('all-read-green-dot','done')
    case('all-read-keeps-done-dot',all_read)

    def next_turn():
        focus(home);send(first,'working');wait_status('working')
        send(first,'done');wait_status('done',1)
        return pixels('next-turn-one-unread','done',True,1)
    case('new-result-rearms-unread',next_turn)

    def corner_removed():
        ctl('tabs','vertical');time.sleep(.2)
        result=shot('no-purple-corners');image=Image.open(result['png']).convert('RGB')
        card_rects=[e['rect'] for e in ctl('dump','#sidebar .tn-dk-c')['elements'] if e.get('visible')]
        for x,y,w,h in card_rects:
            crop=image.crop((round(x+w-4),round(y+h-4),round(x+w+4),round(y+h+4)))
            assert not any(b>90 and r>60 and b>g*1.25 and r>g*1.15 for r,g,b in crop.get_flattened_data())
        return {'cards_checked':len(card_rects),'png':result['png']}
    case('no-leading-purple-corner-dots',corner_removed)

    # Launch real Pi inside an existing shell, with no account/model network.
    for pane in agents:focus(pane)
    focus(home)
    old_panes={p['pane'] for p in snapshot()['panes']}
    snapshot({'op':'new'})
    shell=snapshot()['focused']
    assert shell not in old_panes
    assert next(p for p in snapshot()['panes'] if p['pane']==shell)['kind']=='terminal'
    snapshot({'op':'move','pane':shell,'tab':target_tab})
    pi_dir=root/'pi-agent';pi_dir.mkdir(exist_ok=True)
    (pi_dir/'settings.json').write_text(json.dumps({'quietStartup':True,'compaction':{'enabled':False}}))
    pi_command=shlex.join(['env',f'TERN_CONFIG_DIR={config}',f'PI_CODING_AGENT_DIR={pi_dir}',
        shutil.which('pi'),'--offline','--no-session','--no-extensions','--no-mcp','--no-skills',
        '--no-prompt-templates','--no-context-files','--no-themes','--no-approve','--no-tools','--thinking','off',
        '-e',str(PROJECT/'pi/bridge.ts'),'-e',str(PROJECT/'tests/fixtures/offline_provider.mjs'),
        '--model','tte-offline/test'])
    send(shell,pi_command)
    until(lambda:str(shell) in plugin_state().get('bridge-states',{}),timeout=15)
    focus(home)

    def real_pi_work():
        send(shell,'Run the offline status test.')
        until(lambda:records().get(str(shell),{}).get('status')=='working')
        result=pixels('real-pi-shell-working','working')
        until(lambda:records().get(str(shell),{}).get('status')=='done',timeout=12)
        until(lambda:unread()==1)
        result['completed']=pixels('real-pi-shell-done','done',True,1)
        result['kind']=next(p['kind'] for p in snapshot()['panes'] if p['pane']==shell)
        return result
    case('real-pi-in-ordinary-shell',real_pi_work)

    def real_pi_wait():
        # Review the result first. A later dialog closing must not rearm it.
        focus(shell);until(lambda:unread()==0,label='review ordinary Pi result');focus(home)
        send(shell,'/tte-confirm')
        until(lambda:records().get(str(shell),{}).get('status')=='waiting',label='ordinary Pi confirmation opens')
        result=pixels('real-pi-shell-confirm','waiting')
        snapshot({'op':'send','pane':shell,'text':chr(27)})
        until(lambda:records().get(str(shell),{}).get('status')=='done',label='ordinary Pi confirmation closes')
        assert unread()==0,'closing a dialog rearmed an already viewed result'
        return result
    for round_index in range(args.pi_dialog_rounds):
        case('real-pi-ui-prompt-restores-read-state-'+str(round_index+1),real_pi_wait)
    def bridge_gap():
        focus(shell);until(lambda:unread()==0);focus(home)
        path=config/'plugin-data/tern-tab-enhancer/bridge'/f'{shell}.json'
        backup=root/'bridge-gap.json'
        path.replace(backup)
        until(lambda:str(shell) not in plugin_state().get('bridge-states',{}),label='bridge gap observed')
        assert records()[str(shell)]['read'] is True,'gap erased read record'
        if not path.exists():backup.replace(path)
        else:backup.unlink()
        until(lambda:str(shell) in plugin_state().get('bridge-states',{}),label='bridge recovered')
        time.sleep(.6);assert unread()==0,'same completed generation became unread'
        return pixels('bridge-gap-keeps-read','done')
    case('bridge-gap-preserves-read',bridge_gap)

    def quick_focus():
        focus(shell);send(shell,'Run another offline status test.')
        until(lambda:records().get(str(shell),{}).get('status')=='working')
        path=config/'plugin-data/tern-tab-enhancer/bridge'/f'{shell}.json'
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if path.exists() and json.loads(path.read_text()).get('state')=='done':break
            time.sleep(.005)
        else:raise TimeoutError('Pi completion bridge')
        before_focus=records().get(str(shell),{}).get('status')
        focus(home)
        until(lambda:records().get(str(shell),{}).get('status')=='done')
        assert records()[str(shell)]['read'] is True,'outgoing pane completion was not acknowledged'
        assert unread()==0
        return {'cached_state_before_focus':before_focus,**pixels('quick-focus-keeps-read','done')}
    case('completion-focus-boundary',quick_focus)

    def native_cancel():
        existing={p['pane'] for p in snapshot()['panes']}
        snapshot({'op':'new','command':fixture})
        extra=next(p['pane'] for p in snapshot()['panes'] if p['pane'] not in existing)
        until(lambda:any(a['pane']==extra for a in snapshot()['agents']))
        snapshot({'op':'move','pane':extra,'tab':target_tab});focus(home)
        send(extra,'blocked');until(lambda:records().get(str(extra),{}).get('status')=='waiting')
        result=pixels('native-idle-dialog','waiting')
        send(extra,'idle');until(lambda:records().get(str(extra),{}).get('status')=='idle')
        assert unread()==0,'native cancellation invented an unread result'
        assert records()[str(extra)]['done'] is False
        snapshot({'op':'close','pane':extra})
        return result
    case('native-idle-dialog-cancel-is-not-done',native_cancel)

    def two_windows():
        global control
        primary=control;peer=root/'peer.sock'
        launch('peer-window',['--control',peer,'--out',root/'peer-shots',root],peer)
        try:
            control=peer
            until(lambda:ctl('state').get('gate',{}).get('phase')=='off',timeout=20)
            ctl('tab','new')
            until(lambda:any(s['name']=='plugin:local:tern-tab-enhancer:tabs' for s in ctl('css')['sheets']),timeout=15)
            ctl('tabs','vertical');peer_home=snapshot()['focused']
            snapshot({'op':'new','command':fixture})
            until(lambda:len(snapshot()['agents'])==1)
            peer_first=snapshot()['agents'][0]['pane']
            peer_tab=next(p['tab'] for p in snapshot()['panes'] if p['pane']==peer_first)
            snapshot({'op':'color','tab':peer_tab,'color':'red'})
            snapshot({'op':'split','pane':peer_first,'command':fixture})
            until(lambda:len(snapshot()['agents'])==2)
            peer_agents=[a['pane'] for a in snapshot()['agents']]
            focus(peer_home)
            for pane in peer_agents:send(pane,'working')
            for pane in peer_agents:send(pane,'done')
            until(lambda:all(records().get(str(p),{}).get('done') for p in peer_agents))
            pixels('peer-two-unread','done',True,2)
            focus(peer_first)
            until(lambda:records().get(str(peer_first),{}).get('read') is True)
            control=primary;focus(home)
            for pane in agents:send(pane,'working')
            until(lambda:all(records().get(str(p),{}).get('status')=='working' for p in agents))
            for pane in agents:send(pane,'done')
            until(lambda:all(records().get(str(p),{}).get('done') for p in agents))
            time.sleep(.6);pixels('primary-four-unread','done',True,4)
            command('plugin','reload','--json');time.sleep(.7)
            control=peer;ctl('stats');pixels('peer-read-survives-other-window','done',True,1)
            control=primary;ctl('stats');result=pixels('primary-unread-survives-peer','done',True,4)
            control=peer;ctl('quit')
            return result
        finally:control=primary
    case('two-windows-do-not-overwrite-pane-read-state',two_windows)

    summary['versions']['offline_pi_turns']=2
    summary['versions']['pi']=subprocess.run([shutil.which('pi'),'--version'],capture_output=True,text=True,timeout=10).stdout.strip()

    def uninstall():
        native_colors=[t.get('color') for t in snapshot()['tabs']]
        command('plugin','remove','tern-tab-enhancer','--json');time.sleep(.4)
        assert not any('tern-tab-enhancer' in s['name'] for s in ctl('css')['sheets'])
        assert [t.get('color') for t in snapshot()['tabs']]==native_colors
        settings=json.loads((config/'settings.json').read_text())
        assert 'reduce_motion' not in settings
        return {'colors':native_colors,'reduce_motion_override':False,'png':shot('uninstalled-native-tabs')['png']}
    case('uninstall-restores-native-appearance',uninstall)
    summary['result']='passed'
except Exception as error:
    summary['result']='failed';summary['error']=repr(error)
    try:
        summary['failure_shot']=shot('failure')
        summary['failure_plugin_state']=plugin_state()
        summary['failure_snapshot']=snapshot()
        (root/'failure-capture.txt').write_text(command('capture','@focused','--scrollback')[-20000:])
    except Exception as capture_error:
        summary['capture_error']=repr(capture_error)
    print('FAIL',repr(error),flush=True)
finally:
    for process,output in reversed(owned):
        if process.poll() is None:
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
        output.close()
        for record in summary['processes']:
            if record['pid']==process.pid:record['exit']=process.returncode
    errors=[]
    for log in (root/'logs').glob('*'):
        if log.is_file():
            for line in log.read_text(errors='replace').splitlines():
                if any(word in line for word in ['exceeded','style sheet has errors','plugin window entry','plugin hook failed']):errors.append(line)
    summary['runtime_errors']=errors
    if errors:summary['result']='failed'
    summary['finished']=datetime.now().astimezone().isoformat();save()
    print('SUMMARY',str(root/'summary.json'),flush=True)
raise SystemExit(0 if summary['result']=='passed' else 1)
