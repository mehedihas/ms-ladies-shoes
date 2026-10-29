@echo off
title MS Ladies Shoes - Local Admin Manager
color 0B

echo ================================================================
echo         MS LADIES SHOES - LOCAL PRODUCT MANAGER
echo ================================================================
echo.
echo  Starting local server on port 3570...
echo.

start "MS Ladies Shoes Server" cmd /k "python app.py"
timeout /t 2 /nobreak >nul

echo  Opening Admin Panel in your browser...
start http://localhost:3570/admin/login

echo.
echo ================================================================
echo  HOW TO ADD PRODUCTS:
echo   1. Log in on your browser (Username: Mehedi / Password: Mehedi%%123)
echo   2. Go to "+ Add Product" to add your new shoe models and photos.
echo   3. When you are finished, double-click "push_to_github.bat".
echo      It will immediately upload everything to Vercel!
echo ================================================================
echo.
pause
