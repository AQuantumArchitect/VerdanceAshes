@echo off
REM Quick dial for Verdance difficulty / XP farm without opening JSON.
REM Usage:
REM   SET_DIFFICULTY.bat                 show current
REM   SET_DIFFICULTY.bat 0.85            ease (clearer early campaign)
REM   SET_DIFFICULTY.bat 1.0             standard
REM   SET_DIFFICULTY.bat 1.15            spicy
REM   SET_DIFFICULTY.bat farm            cracked_farm mode
REM   SET_DIFFICULTY.bat standard        standard XP rates
REM   SET_DIFFICULTY.bat xpmult 1.5      farm rate only

setlocal
cd /d "%~dp0"
python -c "import json,sys; from pathlib import Path; p=Path('state/campaign_state.json'); s=json.loads(p.read_text(encoding='utf-8')); pr=s.setdefault('progression',{}); pr.setdefault('mode','cracked_farm'); pr.setdefault('difficultyDial',1.0); pr.setdefault('xpMultiplier',1.0); pr.setdefault('farmSortiesEnabled',True); pr['xpPersistOnDeath']=True; args=sys.argv[1:];
import sys
args=sys.argv[1:]
if not args:
    print(json.dumps(pr, indent=2)); raise SystemExit(0)
a=args[0].lower()
if a in ('farm','cracked','cracked_farm'):
    pr['mode']='cracked_farm'
elif a in ('standard','normal'):
    pr['mode']='standard'
elif a in ('xpmult','xp'):
    pr['xpMultiplier']=float(args[1]) if len(args)>1 else 1.0
else:
    pr['difficultyDial']=max(0.7, min(1.35, float(a)))
p.write_text(json.dumps(s, indent=2)+chr(10), encoding='utf-8')
print('updated progression:')
print(json.dumps(pr, indent=2))
" %*
if errorlevel 1 exit /b 1
echo.
echo Rebuild next mission after dial changes (build_next_mission / play session).
endlocal
