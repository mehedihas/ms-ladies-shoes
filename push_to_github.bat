@echo off
title Push MS Ladies Shoes to GitHub
color 0B
echo ================================================================
echo            PUSHING MS LADIES SHOES TO GITHUB
echo ================================================================
echo.
echo Connecting to GitHub repository: https://github.com/mehedihas/ms-ladies-shoes.git
echo.
echo If a GitHub browser popup appears, click "Sign in with your browser" / "Authorize".
echo.
git push -u origin main
echo.
if %ERRORLEVEL% EQU 0 (
    color 0A
    echo ================================================================
    echo SUCCESS! Your code is now uploaded to GitHub!
    echo Refresh your GitHub page to see your files.
    echo ================================================================
) else (
    color 0C
    echo ================================================================
    echo Push failed. Please check authentication above.
    echo ================================================================
)
echo.
pause
