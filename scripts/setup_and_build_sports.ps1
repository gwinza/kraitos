# Kraitos Sports - bootstrap Node (if missing) and build release APK
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Mobile = Join-Path $Root "mobile\kraitos-sports"
$Tools = Join-Path $Root ".tools"
$NodeDir = Join-Path $Tools "node"

function Ensure-Node {
    if (Get-Command node -ErrorAction SilentlyContinue) {
        Write-Host "Node found: $(node -v)"
        return
    }
    if (Test-Path (Join-Path $NodeDir "node.exe")) {
        $env:PATH = "$NodeDir;$env:PATH"
        Write-Host "Using portable Node: $(node -v)"
        return
    }

    Write-Host "Downloading portable Node.js LTS..."
    New-Item -ItemType Directory -Force -Path $Tools | Out-Null
    $ver = "20.11.0"
    $zip = Join-Path $Tools "node.zip"
    $url = "https://nodejs.org/dist/v$ver/node-v$ver-win-x64.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $Tools -Force
    $extracted = Join-Path $Tools "node-v$ver-win-x64"
    if (Test-Path $NodeDir) { Remove-Item $NodeDir -Recurse -Force }
    Rename-Item $extracted $NodeDir
    Remove-Item $zip -Force
    $env:PATH = "$NodeDir;$env:PATH"
    Write-Host "Installed Node: $(node -v)"
}

function Build-Apk {
    $env:JAVA_HOME = Join-Path $Tools "jdk17"
    $env:ANDROID_HOME = Join-Path $Tools "android\sdk"
    $env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
    $env:NODE_TLS_REJECT_UNAUTHORIZED = "0"
    $env:CI = "1"
    if (Test-Path (Join-Path $env:JAVA_HOME "bin\java.exe")) {
        $env:PATH = "$($env:JAVA_HOME)\bin;$env:PATH"
    }
    $CmdlineBin = Join-Path $env:ANDROID_HOME "cmdline-tools\latest\bin"
    if (Test-Path $CmdlineBin) {
        $env:PATH = "$CmdlineBin;$env:PATH"
    }

    Push-Location $Mobile
    try {
        Write-Host "Installing npm dependencies..."
        npm install --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) {
            Write-Host ""
            Write-Host "npm install failed. See mobile/kraitos-sports/BUILD.md (SSL troubleshooting)."
            return 1
        }

        Write-Host "Generating Android project..."
        npx expo prebuild --platform android --clean
        if ($LASTEXITCODE -ne 0) { return 1 }

        if (-not (Test-Path (Join-Path $env:ANDROID_HOME "platform-tools"))) {
            Write-Host ""
            Write-Host "Android SDK packages not installed."
            Write-Host "Run: powershell -File scripts\install_android_sdk.ps1"
            Write-Host "Requires Java 17 at .tools\jdk17 and network access to Google."
            Write-Host "Or use cloud build: npm run build:apk:cloud"
            return 1
        }

        Push-Location android
        .\gradlew.bat assembleRelease
        $apk = "app\build\outputs\apk\release\app-release.apk"
        if (Test-Path $apk) {
            $dest = Join-Path $Root "dist\kraitos-sports.apk"
            New-Item -ItemType Directory -Force -Path (Join-Path $Root "dist") | Out-Null
            Copy-Item $apk $dest -Force
            Write-Host ""
            Write-Host "SUCCESS: APK at $dest"
            return 0
        }
        return 1
    } finally {
        Pop-Location
    }
}

Ensure-Node
exit (Build-Apk)
