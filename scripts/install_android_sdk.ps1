# Install minimal Android SDK for local APK build
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Tools = Join-Path $Root ".tools"
$SdkRoot = Join-Path $Tools "android\sdk"
$JdkDir = Join-Path $Tools "jdk17"
$Cmdline = Join-Path $SdkRoot "cmdline-tools\latest"

# JDK 17 required (sdkmanager needs Java 17+)
if (-not (Test-Path (Join-Path $JdkDir "bin\java.exe"))) {
    Write-Host "JDK 17 not found at $JdkDir"
    Write-Host "Run setup_and_build_sports.ps1 first (downloads JDK automatically on first full build)."
    exit 1
}

$env:JAVA_HOME = $JdkDir
$env:ANDROID_HOME = $SdkRoot
$env:ANDROID_SDK_ROOT = $SdkRoot
$env:PATH = "$JdkDir\bin;$Cmdline\bin;$SdkRoot\platform-tools;$env:PATH"

if (-not (Test-Path (Join-Path $Cmdline "bin\sdkmanager.bat"))) {
    Write-Host "Downloading Android command-line tools..."
    $zip = Join-Path $Tools "cmdline-tools.zip"
    $url = "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $Tools -Force
    New-Item -ItemType Directory -Force -Path (Join-Path $SdkRoot "cmdline-tools\latest") | Out-Null
    Move-Item (Join-Path $Tools "cmdline-tools\*") (Join-Path $SdkRoot "cmdline-tools\latest") -Force
    Remove-Item $zip -Force
}

Write-Host "Installing SDK packages (requires network access to Google)..."
$packages = @(
    "platform-tools",
    "platforms;android-34",
    "build-tools;34.0.0"
)
foreach ($pkg in $packages) {
    Write-Host "  -> $pkg"
    echo y | & "$Cmdline\bin\sdkmanager.bat" $pkg 2>&1 | Out-Null
}

Write-Host "ANDROID_HOME=$SdkRoot"
Write-Host "SDK install complete."
