# Build Kraitos Sports APK

## Prerequisites

- Node.js 18+
- Python 3.11+ with `pip install -r requirements.txt -r requirements-sports.txt`
- For local APK: Android SDK + Java 17, OR Expo account for cloud build

## 1. Start the API (optional — app works offline in demo mode)

```powershell
cd C:\Users\Asus\kraitos
python run_sports_api.py
```

## 2. Export fresh demo data for offline mode

```powershell
python scripts/export_sports_demo.py
```

## 3. Install mobile dependencies

```powershell
cd mobile\kraitos-sports
npm install
```

### If npm fails with `UNABLE_TO_VERIFY_LEAF_SIGNATURE`

Common on corporate networks or proxy/VPN setups. Try in order:

1. **Use your system Node** (outside Cursor sandbox) instead of `.tools/node`
2. **Point npm at your corporate CA** (preferred):
   ```powershell
   npm config set cafile "C:\path\to\your\corp-root-ca.pem"
   npm install
   ```
3. **Temporary workaround** (less secure — use only if IT confirms):
   ```powershell
   npm config set strict-ssl false
   npm install
   ```

Portable Node from `scripts/setup_and_build_sports.ps1` is at `.tools/node` if you need it:
```powershell
$env:PATH = "C:\Users\Asus\kraitos\.tools\node;$env:PATH"
```

## 4. Build APK

**Progress so far (automated):** `npm install` and `expo prebuild` can run via `scripts\setup_and_build_sports.ps1`.
Portable Node, JDK 17, and Android cmdline tools are stored under `.tools\`.

**Final step (needs Google SDK download):**

```powershell
# From repo root - install SDK platform-tools + build-tools
powershell -ExecutionPolicy Bypass -File scripts\install_android_sdk.ps1

# Build release APK
cd mobile\kraitos-sports\android
$env:JAVA_HOME = "C:\Users\Asus\kraitos\.tools\jdk17"
$env:ANDROID_HOME = "C:\Users\Asus\kraitos\.tools\android\sdk"
.\gradlew.bat assembleRelease
```

Output: `android\app\build\outputs\apk\release\app-release.apk`

Or copy to `dist\`:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_and_build_sports.ps1
```

### Option A — EAS Cloud (no local Android SDK)

```powershell
npm install -g eas-cli
eas login
npm run build:apk:cloud
```

### Option B — Local build (requires Android SDK)

```powershell
npx expo prebuild --platform android
cd android
.\gradlew assembleRelease
```

APK output: `android\app\build\outputs\apk\release\app-release.apk`

### Option C — Development on device/emulator

```powershell
npx expo start
```

Press `a` for Android emulator.

## Philosophy

**Kraitos does not pick winners. Kraitos finds edges.**

Data → Probability → Value → Risk → Decision
