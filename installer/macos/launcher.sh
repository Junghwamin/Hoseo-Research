#!/bin/bash
# ===========================================================================
# 호서대학교 정화민 - 연구실적 분석 포털 - macOS 런처
#
# .app 번들 내의 Standalone Python으로 Streamlit 서버를 시작하고
# 브라우저를 연다.
#
# 앱 데이터(output, Raw data, .env 등)는 번들 외부의
# ~/Library/Application Support/HoseoIRPortal/ 에 저장한다.
# (.app 번들 내부는 macOS 보안 정책상 읽기 전용)
# ===========================================================================

DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
APP_DIR="$DIR/app"
PYTHON_DIR="$DIR/python"
PYTHON="$PYTHON_DIR/bin/python3"
PORT=8501

# Python 바이너리 존재 확인
if [ ! -f "$PYTHON" ]; then
    osascript -e 'display dialog "Python을 찾을 수 없습니다.\n경로: '"$PYTHON"'" buttons {"확인"} with icon stop'
    exit 1
fi

# --- 쓰기 가능한 데이터 디렉토리 설정 ---
DATA_DIR="$HOME/Library/Application Support/HoseoIRPortal"
mkdir -p "$DATA_DIR/output/reports"
mkdir -p "$DATA_DIR/Raw data"

# .streamlit 설정 복사 (최초 실행 시)
if [ ! -d "$DATA_DIR/.streamlit" ]; then
    cp -R "$APP_DIR/.streamlit" "$DATA_DIR/.streamlit"
    rm -f "$DATA_DIR/.streamlit/secrets.toml"  # 사용자 데이터 영역에도 시크릿을 두지 않는다
fi

# config 복사 (최초 실행 시)
if [ ! -d "$DATA_DIR/config" ]; then
    cp -R "$APP_DIR/config" "$DATA_DIR/config"
fi

export PYTHONPATH="$APP_DIR"
export STREAMLIT_SERVER_HEADLESS=true
export STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
export PATH="$PYTHON_DIR/bin:$PATH"

# 사용 가능한 포트 찾기
find_free_port() {
    local port=$PORT
    while [ $port -le 8510 ]; do
        if ! lsof -i :$port > /dev/null 2>&1; then
            echo $port
            return
        fi
        port=$((port + 1))
    done
    echo $PORT
}

PORT=$(find_free_port)

# 작업 디렉토리를 데이터 디렉토리로 설정
# (앱 코드의 상대경로 output/, Raw data/, .env 등이 여기에 생성됨)
cd "$DATA_DIR"

# Streamlit 서버 시작 (백그라운드)
"$PYTHON" -m streamlit run "$APP_DIR/report_app/app.py" \
    --server.headless true \
    --server.port "$PORT" &

SERVER_PID=$!

# 서버 준비 대기
echo "서버 시작 대기 중..."
for i in $(seq 1 60); do
    if curl -s "http://localhost:$PORT" > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# 브라우저 열기
open "http://localhost:$PORT"

# 서버 프로세스 대기 (종료 시까지)
wait $SERVER_PID
