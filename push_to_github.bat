@echo off
title Push MS Ladies Shoes to GitHub
color 0B
echo ================================================================
echo            PUSHING MS LADIES SHOES TO GITHUB
echo ================================================================
echo.
echo Connecting to GitHub repository: https://github.com/mehedihas/ms-ladies-shoes.git
echo.
echo  [1/3] Adding all product changes, database, and photos...
git add .
echo.
echo  [2/3] Saving latest products and database updates...
git commit -m "Update products, catalog and database" 2>nul
echo.
echo  [3/3] Uploading to GitHub...
git push origin main
echo.
if %ERRORLEVEL% EQU 0 (
    color 0A
    echo ================================================================
    echo SUCCESS! Your changes, products and photos are on GitHub!
    echo.
    echo Vercel is now automatically rebuilding and deploying your site:
    echo 👉 https://mscollections.vercel.app
    echo (Live updates usually appear within 45-60 seconds)
    echo ================================================================
) else (
    color 0C
    echo ================================================================
    echo Push failed. Please check internet or GitHub credentials.
    echo ================================================================
)
echo.
pause
