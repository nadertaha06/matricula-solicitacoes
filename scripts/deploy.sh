#!/usr/bin/env bash
set -Eeuo pipefail
image=${1:?Informe a imagem com tag do commit}
service=matricula-solicitacoes
port=8002
env_file="$HOME/.config/matricula/$service.env"
test -s "$env_file"
# Serialize deployments to protect a small shared EC2 from simultaneous image pulls.
exec 9>"$HOME/.config/matricula/deploy.lock"
flock -w 300 9
docker pull "$image"
previous=$(docker inspect --format '{{.Config.Image}}' "$service" 2>/dev/null || true)
previous_id=$(docker inspect --format '{{.Image}}' "$service" 2>/dev/null || true)
run_container() {
  docker run -d --name "$service" --network rede --restart unless-stopped \
    --label projeto=matricula --env-file "$env_file" -p "127.0.0.1:$port:$port" "$1"
}
if docker inspect "$service" >/dev/null 2>&1; then
  docker stop --time 20 "$service"
  docker rm "$service"
fi
rollback() {
  docker logs --tail 40 "$service" 2>/dev/null || true
  docker rm -f "$service" >/dev/null 2>&1 || true
  if [ -n "$previous" ]; then run_container "$previous"; fi
  echo "Deploy falhou; imagem anterior restaurada quando disponivel." >&2
  exit 1
}
# The EC2 disk is small: keep only the new image and the previous one ("$previous") of this repository.
# Images still used by a container are refused by docker and kept.
prune_images() {
  local current ref id
  current=$(docker image inspect --format '{{.Id}}' "$image") || return 0
  docker image ls --no-trunc --format '{{.Repository}}:{{.Tag}} {{.ID}}' "${image%:*}" |
    while read -r ref id; do
      if [ "$id" = "$current" ] || [ "$id" = "$previous_id" ]; then continue; fi
      case "$ref" in *:'<none>') ref=$id ;; esac
      docker image rm "$ref" >/dev/null 2>&1 || true
    done
}
run_container "$image" || rollback
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 2 "http://127.0.0.1:$port/ready" >/dev/null; then
    echo "$service pronto: $image"
    prune_images || true
    exit 0
  fi
  sleep 2
done
rollback
