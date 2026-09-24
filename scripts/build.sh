#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/android"
OUT="$ROOT/out"

ANDROID_HOME="${ANDROID_HOME:-/opt/android-sdk}"
PLATFORM="${ANDROID_PLATFORM:-35}"
BUILD_TOOLS="${ANDROID_BUILD_TOOLS:-35.0.0}"

AAPT="$ANDROID_HOME/build-tools/$BUILD_TOOLS/aapt2"
D8="$ANDROID_HOME/build-tools/$BUILD_TOOLS/d8"
ZIPALIGN="$ANDROID_HOME/build-tools/$BUILD_TOOLS/zipalign"
APKSIGNER="$ANDROID_HOME/build-tools/$BUILD_TOOLS/apksigner"
ANDROID_JAR="$ANDROID_HOME/platforms/android-$PLATFORM/android.jar"

rm -rf "$OUT"
mkdir -p "$OUT/gen" "$OUT/classes" "$OUT/dex"

"$AAPT" compile --dir "$APP/res" -o "$OUT/res.zip"
"$AAPT" link -o "$OUT/unsigned.apk"   -I "$ANDROID_JAR"   --manifest "$APP/AndroidManifest.xml"   --java "$OUT/gen"   "$OUT/res.zip"

javac -source 8 -target 8 -encoding UTF-8   -cp "$ANDROID_JAR"   -d "$OUT/classes"   $(find "$OUT/gen" "$APP/src" -name '*.java')

"$D8" --lib "$ANDROID_JAR"   --output "$OUT/dex"   $(find "$OUT/classes" -name '*.class')

python3 - "$OUT/unsigned.apk" "$OUT/dex/classes.dex" <<'PY'
import sys
from zipfile import ZipFile, ZIP_DEFLATED

apk, dex = sys.argv[1:3]
with ZipFile(apk, "a", compression=ZIP_DEFLATED) as z:
    z.write(dex, "classes.dex")
PY

"$ZIPALIGN" -f 4 "$OUT/unsigned.apk" "$OUT/Yingbao-aligned.apk"

if [[ -n "${YINGBAO_KEYSTORE:-}" ]]; then
  : "${YINGBAO_STOREPASS:?Set YINGBAO_STOREPASS}"
  : "${YINGBAO_KEYPASS:?Set YINGBAO_KEYPASS}"
  "$APKSIGNER" sign     --ks "$YINGBAO_KEYSTORE"     --ks-key-alias "${YINGBAO_KEY_ALIAS:-yingbao}"     --ks-pass "pass:$YINGBAO_STOREPASS"     --key-pass "pass:$YINGBAO_KEYPASS"     --out "$OUT/Yingbao.apk"     "$OUT/Yingbao-aligned.apk"
  "$APKSIGNER" verify --verbose "$OUT/Yingbao.apk"
  echo "Built signed APK: $OUT/Yingbao.apk"
else
  echo "Built unsigned/aligned APK: $OUT/Yingbao-aligned.apk"
fi
