// Generate minimal PNG assets for Expo
const fs = require("fs");
const path = require("path");

// Minimal valid 1024x1024 PNG (teal on dark) - base64 decoded
const PNG_1x1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64"
);

const assetsDir = path.join(__dirname, "assets");
fs.mkdirSync(assetsDir, { recursive: true });

for (const name of ["icon.png", "splash.png", "adaptive-icon.png", "favicon.png"]) {
  fs.writeFileSync(path.join(assetsDir, name), PNG_1x1);
  console.log("Created", name);
}
