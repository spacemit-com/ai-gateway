#!/usr/bin/env bash
# 清理 spacemit-ai-gateway Rerank 缓存工具

DB="$HOME/.cache/spacemit-ai-gateway/rerank/db.sqlite"
MODELS_DIR="$HOME/.cache/spacemit-ai-gateway/rerank/models"

PORT=18790

usage() {
  echo "用法: $0 [db|models|kill|killall|all]"
  echo "  db      — 删除数据库 ($DB)"
  echo "  models  — 删除所有模型文件 ($MODELS_DIR/*.gguf)"
  echo "  kill    — 杀掉占用端口 $PORT 的进程"
  echo "  killall — 杀掉所有 llama-server 进程"
  echo "  all     — 删除数据库 + 所有模型文件 + 杀掉所有 llama-server 进程"
}

delete_db() {
  if [ -f "$DB" ]; then
    rm "$DB" && echo "已删除: $DB"
  else
    echo "数据库不存在: $DB"
  fi
}

delete_models() {
  shopt -s nullglob
  files=("$MODELS_DIR"/*.gguf)
  if [ ${#files[@]} -eq 0 ]; then
    echo "无模型文件: $MODELS_DIR"
    return
  fi
  for f in "${files[@]}"; do
    rm "$f" && echo "已删除: $f"
  done
}

kill_port() {
  local pids
  pids=$(lsof -ti tcp:"$PORT" 2>/dev/null)
  if [ -z "$pids" ]; then
    echo "端口 $PORT 无占用进程"
    return
  fi
  echo "$pids" | xargs kill -9
  echo "已杀掉端口 $PORT 的进程: $pids"
}

kill_llama() {
  local pids
  pids=$(pgrep -f 'llama-server' 2>/dev/null)
  if [ -z "$pids" ]; then
    echo "无 llama-server 进程"
    return
  fi
  echo "$pids" | xargs kill -9
  echo "已杀掉所有 llama-server 进程: $(echo "$pids" | tr '\n' ' ')"
}

case "${1:-}" in
  db)      delete_db ;;
  models)  delete_models ;;
  kill)    kill_port ;;
  killall) kill_llama ;;
  all)     delete_db; delete_models; kill_llama ;;
  *)       usage; exit 1 ;;
esac
