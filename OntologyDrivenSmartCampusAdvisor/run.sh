#!/usr/bin/env bash
# 启动 Smart Campus Advisor Web 服务
# 用法:
#   ./run.sh              # 如端口被占用则先 kill，再启动
#   ./run.sh -p 8773      # 自定义端口
#   ./run.sh -f           # 强制 kill 占用端口的进程（无需确认）
#   ./run.sh -k           # 仅 kill 占用进程，不启动服务

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT=8772
FORCE=0
ONLY_KILL=0

usage() {
    cat <<EOF
用法: $0 [-p PORT] [-f] [-k]
  -p PORT    指定端口（默认 8772）
  -f         强制 kill 占用端口的进程，无需交互确认
  -k         仅清理占用端口的进程，不启动服务
  -h         显示帮助
EOF
}

while getopts ":p:fkh" opt; do
    case "$opt" in
        p) PORT="$OPTARG" ;;
        f) FORCE=1 ;;
        k) ONLY_KILL=1 ;;
        h) usage; exit 0 ;;
        \?) echo "未知参数: -$OPTARG"; usage; exit 2 ;;
        :)  echo "参数 -$OPTARG 需要值"; usage; exit 2 ;;
    esac
done

if ! command -v python3 >/dev/null 2>&1; then
    echo "[错误] 未找到 python3，请先安装 Python 3"
    exit 1
fi

if [[ ! -f "server.py" ]]; then
    echo "[错误] 未在 $(pwd) 找到 server.py"
    exit 1
fi

list_occupants() {
    # 仅匹配 LISTEN 状态的进程，过滤本脚本自身的 grep
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null \
        | grep -v "^$$\$" \
        | sort -u
}

kill_occupants() {
    local pids
    pids="$(list_occupants)"
    if [[ -z "$pids" ]]; then
        echo "[端口] $PORT 当前空闲"
        return 0
    fi

    echo "[端口] $PORT 被以下进程占用:"
    for pid in $pids; do
        local cmd
        cmd="$(ps -p "$pid" -o command= 2>/dev/null | head -c 120)"
        echo "        PID=$pid -> $cmd"
    done

    if [[ $FORCE -eq 0 ]]; then
        local reply
        read -r -p "      是否 kill 这些进程后继续? [y/N] " reply
        case "$reply" in
            y|Y|yes|YES) ;;
            *) echo "[取消] 未执行 kill，退出"; exit 1 ;;
        esac
    fi

    local failed=0
    for pid in $pids; do
        if kill "$pid" 2>/dev/null; then
            echo "[kill] 已发送 SIGTERM 给 PID=$pid"
        else
            echo "[kill] 无法终止 PID=$pid（可能已退出）"
            continue
        fi
    done

    # 等待端口释放
    local waited=0
    while (( waited < 10 )); do
        if [[ -z "$(list_occupants)" ]]; then
            echo "[端口] $PORT 已释放"
            return 0
        fi
        sleep 0.5
        waited=$((waited + 1))
    done

    # 还有残留则强制 kill
    local remaining
    remaining="$(list_occupants)"
    if [[ -n "$remaining" ]]; then
        echo "[kill] 部分进程未响应 SIGTERM，发送 SIGKILL"
        for pid in $remaining; do
            kill -9 "$pid" 2>/dev/null && echo "[kill] SIGKILL -> PID=$pid"
        done
        sleep 0.5
    fi

    if [[ -n "$(list_occupants)" ]]; then
        echo "[错误] 端口 $PORT 仍被占用，无法启动"
        return 1
    fi
    echo "[端口] $PORT 已释放"
    return 0
}

cleanup() {
    local exit_code=$?
    if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        echo
        echo "[退出] 终止服务进程 PID=$SERVER_PID"
        kill "$SERVER_PID" 2>/dev/null
        wait "$SERVER_PID" 2>/dev/null
    fi
    exit "$exit_code"
}

# 进入工作目录后再处理端口
kill_occupants || exit 1

if [[ $ONLY_KILL -eq 1 ]]; then
    exit 0
fi

echo "[启动] 在 $(pwd) 启动 server.py (端口 $PORT)"
trap cleanup INT TERM EXIT

python3 server.py &
SERVER_PID=$!

# 前台等待，确保 Ctrl+C 能正常传递到子进程
wait "$SERVER_PID"