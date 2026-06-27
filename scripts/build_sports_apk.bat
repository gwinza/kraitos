@echo off
REM Build Kraitos Sports release APK (requires Android SDK)
cd /d "%~dp0..\mobile\kraitos-sports"
call npm install
if errorlevel 1 exit /b 1
call npx expo prebuild --platform android --clean
if errorlevel 1 exit /b 1
cd android
call gradlew.bat assembleRelease
if errorlevel 1 exit /b 1
echo.
echo APK built: android\app\build\outputs\apk\release\app-release.apk
pause
