$ErrorActionPreference = "Stop"

$Repo = "C:\Users\Asus\kraitos"
$Project = "$Repo\mobile\kraitos-sports"
$Sdk = "$Repo\.tools\android\sdk"
$Jdk = "$Repo\.tools\jdk17"
$Node = "$Repo\.tools\node"
$Gradle = "$Repo\.tools\gradle-8.8"
$Cache = "C:\g3"
$Tmp = "C:\t"
$Dist = "$Repo\dist"

New-Item -ItemType Directory -Force -Path $Cache, $Tmp, $Dist | Out-Null

foreach ($drive in @("K:", "S:", "N:", "L:")) {
  subst $drive /D 2>$null | Out-Null
}
subst K: $Project
subst S: $Sdk
subst N: $Node
subst L: $Gradle

$env:JAVA_HOME = $Jdk
$env:ANDROID_HOME = "S:\"
$env:ANDROID_SDK_ROOT = "S:\"
$env:GRADLE_USER_HOME = $Cache
$env:TEMP = $Tmp
$env:TMP = $Tmp
$env:GRADLE_OPTS = "-Djavax.net.ssl.trustStoreType=Windows-ROOT -Dorg.gradle.daemon=false"
$env:PATH = "$Jdk\bin;S:\platform-tools;N:\;$env:PATH"

Write-Host "Stopping old Gradle daemons..."
& "L:\bin\gradle.bat" --stop | Out-Host

Write-Host "Verifying prerequisites..."
if (!(Test-Path "K:\android\settings.gradle")) { throw "Android project missing. Run expo prebuild first." }
if (!(Test-Path "S:\platforms\android-34\android.jar")) { throw "Android SDK Platform 34 missing." }
if (!(Test-Path "S:\build-tools\34.0.0\aapt2.exe")) { throw "Android build-tools 34 missing." }
if (!(Test-Path "$Jdk\bin\java.exe")) { throw "JDK 17 missing." }

Write-Host "Building release APK from short path K:\android..."
Push-Location "K:\android"
try {
  & "L:\bin\gradle.bat" assembleRelease --no-daemon --no-parallel --max-workers=2 --no-build-cache --stacktrace
  if ($LASTEXITCODE -ne 0) { throw "Gradle failed with exit code $LASTEXITCODE" }
} finally {
  Pop-Location
}

$apk = "K:\android\app\build\outputs\apk\release\app-release.apk"
if (!(Test-Path $apk)) { throw "Build finished but APK was not found at $apk" }
$dest = "$Dist\kraitos-sports.apk"
Copy-Item $apk $dest -Force
Write-Host "SUCCESS: $dest"
