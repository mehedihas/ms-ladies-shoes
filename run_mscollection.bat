@echo off
title MS Ladies Shoes - Online Server (mscollection.loca.lt)
color 0B

echo ================================================================
echo         MS LADIES SHOES - ONLINE PUBLIC SERVER
echo ================================================================
echo.
echo  [1/2] Launching Flask Server on port 3570...
echo.

start "Flask Backend (Port 3570)" cmd /k "python app.py"
timeout /t 3 /nobreak >nul

echo  [2/2] Opening Public Tunnel...
echo ================================================================
echo  IMPORTANT: KEEP THIS WINDOW OPEN while users browse your shop!
echo  Your Public Website Link: https://mscollection.loca.lt
echo ================================================================
echo.

:TUNNEL_LOOP
npx -y localtunnel --port 3570 --subdomain mscollection
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo LocalTunnel busy or disconnected. Trying SSH Tunnel (localhost.run)...
    ssh -o StrictHostKeyChecking=no -R 80:localhost:3570 nokey@localhost.run
)

echo.
echo Tunnel connection dropped. Reconnecting in 3 seconds...
timeout /t 3 /nobreak >nul
goto TUNNEL_LOOP
