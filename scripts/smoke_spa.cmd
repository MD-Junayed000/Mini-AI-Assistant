@echo off
cd /d d:\Mini_AI_Assistant
start /b "" uvicorn main:app --host 127.0.0.1 --port 8790 > logs\smoke8790.out 2> logs\smoke8790.err
ping 127.0.0.1 -n 8 > nul
echo === healthz ===
powershell -Command "try { (Invoke-WebRequest http://127.0.0.1:8790/healthz -UseBasicParsing).Content } catch { 'ERR ' + $_.Exception.Message }"
echo === / ===
powershell -Command "try { ((Invoke-WebRequest http://127.0.0.1:8790/ -UseBasicParsing).Content).Substring(0,200) } catch { 'ERR ' + $_.Exception.Message }"
echo === /assets/JS ===
powershell -Command "try { 'len=' + ((Invoke-WebRequest http://127.0.0.1:8790/assets/index-Dg5npmHy.js -UseBasicParsing).Content).Length } catch { 'ERR ' + $_.Exception.Message }"
echo === /random/spa ===
powershell -Command "try { ((Invoke-WebRequest http://127.0.0.1:8790/random/spa -UseBasicParsing).Content).Substring(0,80) } catch { 'ERR ' + $_.Exception.Message }"
echo === /metrics ===
powershell -Command "try { ((Invoke-WebRequest http://127.0.0.1:8790/metrics -UseBasicParsing).Content).Substring(0,200) } catch { 'ERR ' + $_.Exception.Message }"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r :8790.*LISTENING') do taskkill /pid %%a /f > nul 2>&1