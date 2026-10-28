@echo off
title MS Ladies Shoes - Public Online Server
color 0A

echo ================================================================
echo               MS LADIES SHOES - PUBLIC ONLINE SERVER
echo ================================================================
echo.
echo  [1/2] Starting Flask backend server on port 3570...
echo.

start "MS Ladies Shoes Backend" cmd /k "python app.py"
timeout /t 3 /nobreak >nul

echo.
echo  [2/2] Select Online Link Type:
echo.
echo  [1] Custom Subdomain: https://mscollection.loca.lt (LocalTunnel)
echo  [2] Instant SSH Tunnel via localhost.run
echo.
set /p choice="Enter choice (1 or 2, default is 1): "

if "%choice%"=="2" goto SSH_LOOP

:LT_LOOP
echo.
echo Connecting to https://mscollection.loca.lt ...
echo KEEP THIS WINDOW OPEN!
npx -y localtunnel --port 3570 --subdomain mscollection
echo Tunnel disconnected. Reconnecting in 3 seconds...
timeout /t 3 /nobreak >nul
goto LT_LOOP

:SSH_LOOP
echo.
echo Connecting to localhost.run SSH Tunnel...
echo KEEP THIS WINDOW OPEN!
ssh -o StrictHostKeyChecking=no -R 80:localhost:3570 nokey@localhost.run
echo Tunnel disconnected. Reconnecting in 3 seconds...
timeout /t 3 /nobreak >nul
goto SSH_LOOP
