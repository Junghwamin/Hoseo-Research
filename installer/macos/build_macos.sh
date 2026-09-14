#!/bin/bash
# ===========================================================================
# 호서대학교 정화민 - 연구실적 분석 포털 - macOS 빌드 스크립트
#
# python-build-standalone(완전 독립형 Python)을 번들에 내장하여
# 대상 Mac에 Python이 없어도 실행 가능한 .app + .dmg를 생성한다.
#
# 사용법:
#   bash installer/macos/build_macos.sh
#
# 요구사항:
#   - macOS 11.0+ (GitHub Actions macos-latest에서 실행 권장)
#   - curl, tar, hdiutil (macOS 기본 제공)
# ===========================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build/macos"
APP_NAME="연구실적 분석 포털"
APP_BUNDLE="$BUILD_DIR/${APP_NAME}.app"
DIST_DIR="$PROJECT_ROOT/dist/macos"
APP_VERSION="5.0"

# python-build-standalone 릴리즈 (완전 독립형, relocatable)
# https://github.com/astral-sh/python-build-standalone/releases
PYTHON_BUILD_TAG="20251120"
PYTHON_VERSION="3.11.14"

# 현재 아키텍처 감지 (arm64 또는 x86_64)
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then
    PYTHON_TRIPLE="aarch64-apple-darwin"
else
    PYTHON_TRIPLE="x86_64-apple-darwin"
fi

# URL의 + 문자를 %2B로 인코딩
PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PYTHON_BUILD_TAG}/cpython-${PYTHON_VERSION}%2B${PYTHON_BUILD_TAG}-${PYTHON_TRIPLE}-install_only.tar.gz"

echo "=========================================="
echo "  연구실적 분석 포털 - macOS 빌드"
echo "  아키텍처: $ARCH"
echo "=========================================="

# --- 1. 빌드 디렉토리 초기화 ---
echo ""
echo "[1/6] 빌드 디렉토리 초기화..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# --- 2. Standalone Python 다운로드 ---
echo ""
echo "[2/6] Standalone Python 다운로드..."
echo "  URL: $PYTHON_URL"
PYTHON_TAR="$BUILD_DIR/python-standalone.tar.gz"
curl -L -o "$PYTHON_TAR" "$PYTHON_URL"

echo "  압축 해제..."
STANDALONE_DIR="$BUILD_DIR/python-standalone"
mkdir -p "$STANDALONE_DIR"
tar -xzf "$PYTHON_TAR" -C "$STANDALONE_DIR"
rm "$PYTHON_TAR"

# python-build-standalone은 python/ 디렉토리로 추출됨
PYTHON_ROOT="$STANDALONE_DIR/python"
PYTHON_BIN="$PYTHON_ROOT/bin/python3"

echo "  Python 경로: $PYTHON_BIN"
"$PYTHON_BIN" --version

# --- 3. 의존성 설치 ---
echo ""
echo "[3/6] 의존성 설치..."
"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r "$PROJECT_ROOT/requirements.txt"
echo "  의존성 설치 완료"

# --- 4. .app 번들 구조 생성 ---
echo ""
echo "[4/6] .app 번들 구조 생성..."
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources/app"
mkdir -p "$APP_BUNDLE/Contents/Resources/app/output/reports"
mkdir -p "$APP_BUNDLE/Contents/Resources/app/Raw data"

# Info.plist 복사
cp "$SCRIPT_DIR/Info.plist" "$APP_BUNDLE/Contents/Info.plist"
# Info.plist 버전 업데이트
sed -i '' "s/__APP_VERSION__/$APP_VERSION/g" "$APP_BUNDLE/Contents/Info.plist"

# 아이콘 복사 (있으면)
if [ -f "$SCRIPT_DIR/icon.icns" ]; then
    cp "$SCRIPT_DIR/icon.icns" "$APP_BUNDLE/Contents/Resources/icon.icns"
fi

# --- 5. 앱 파일 및 Python 환경 복사 ---
echo ""
echo "[5/6] 파일 복사..."

# Standalone Python 전체를 번들에 복사
cp -R "$PYTHON_ROOT" "$APP_BUNDLE/Contents/Resources/python"

# 앱 소스 코드 복사
cp -R "$PROJECT_ROOT/report_app" "$APP_BUNDLE/Contents/Resources/app/report_app"
cp -R "$PROJECT_ROOT/config" "$APP_BUNDLE/Contents/Resources/app/config"
# secrets.toml 은 절대 번들에 넣지 않는다. 유지보수자가 로컬 테스트용으로
# .streamlit/secrets.toml 을 만들어 둔 상태에서 빌드하면 실제 API Key 가
# 배포 .dmg 안으로 들어간다(.gitignore 는 git 만 막고 빌드는 못 막는다).
cp -R "$PROJECT_ROOT/.streamlit" "$APP_BUNDLE/Contents/Resources/app/.streamlit"
rm -f "$APP_BUNDLE/Contents/Resources/app/.streamlit/secrets.toml"
cp "$PROJECT_ROOT/전임교원_연구실적_전처리.py" "$APP_BUNDLE/Contents/Resources/app/"
cp "$PROJECT_ROOT/requirements.txt" "$APP_BUNDLE/Contents/Resources/app/"

# __pycache__ 삭제
find "$APP_BUNDLE" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# 런처 스크립트 복사 (실행 가능하게)
cp "$SCRIPT_DIR/launcher.sh" "$APP_BUNDLE/Contents/MacOS/launcher"
chmod +x "$APP_BUNDLE/Contents/MacOS/launcher"

# --- 6. DMG 생성 ---
echo ""
echo "[6/6] DMG 생성..."
mkdir -p "$DIST_DIR"
DMG_PATH="$DIST_DIR/HoseoIR_Setup_v${APP_VERSION}.dmg"

# 기존 DMG 삭제
rm -f "$DMG_PATH"

hdiutil create \
    -volname "$APP_NAME" \
    -srcfolder "$APP_BUNDLE" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

echo ""
echo "=========================================="
echo "  빌드 완료!"
echo "  .app: $APP_BUNDLE"
echo "  .dmg: $DMG_PATH"
echo "=========================================="
