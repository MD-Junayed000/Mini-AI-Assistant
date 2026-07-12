@echo off
cd /d d:\Mini_AI_Assistant
start /b "" uvicorn main:app --host 127.0.0.1 --port 8791 > logs\smoke8791.out 2> logs\smoke8791.err
ping 127.0.0.1 -n 8 > nul
echo === healthz ===
powershell -Command "try { (Invoke-WebRequest http://127.0.0.1:8791/healthz -UseBasicParsing).Content } catch { 'ERR ' + $_.Exception.Message }"
echo === / (API catalog) ===
powershell -Command "try { ((Invoke-WebRequest http://127.0.0.1:8791/ -UseBasicParsing).Content).Substring(0,120) } catch { 'ERR ' + $_.Exception.Message }"
echo === /app (SPA root) ===
powershell -Command "try { ((Invoke-WebRequest http://127.0.0.1:8791/app -UseBasicParsing).Content).Substring(0,120) } catch { 'ERR ' + $_.Exception.Message }"
echo === /app/some/deep/route (SPA catch-all) ===
powershell -Command "try { ((Invoke-WebRequest http://127.0.0.1:8791/app/some/deep/route -UseBasicParsing).Content).Substring(0,120) } catch { 'ERR ' + $_.Exception.Message }"
echo === /assets/JS ===
powershell -Command "try { 'len=' + ((Invoke-WebRequest http://127.0.0.1:8791/assets/index-Dg5npmHy.js -UseBasicParsing).Content).Length } catch { 'ERR ' + $_.Exception.Message }"
echo === /favicon.png ===
powershell -Command "try { 'len=' + ((Invoke-WebRequest http://127.0.0.1:8791/favicon.png -UseBasicParsing).Content).Length } catch { 'ERR ' + $_.Exception.Message }"
echo === /random/spa (root catch-all) ===
powershell -Command "try { ((Invoke-WebRequest http://127.0.0.1:8791/random/spa -UseBasicParsing).Content).Substring(0,80) } catch { 'ERR ' + $_.Exception.Message }"
echo === /metrics (head) ===
powershell -Command "try { ((Invoke-WebRequest http://127.0.0.1:8791/metrics -UseBasicParsing).Content).Substring(0,80) } catch { 'ERR ' + $_.Exception.Message }"
for /f "tokens=5" %%a in ('netstat -aon ^| findstr /r :8791.*LISTENING') do taskkill /pid %%a /f > nul 2>&1