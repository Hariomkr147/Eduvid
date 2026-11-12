#!/bin/bash
# Checks the Caddyfile's upload limit with a throwaway Caddy on plain HTTP inside the stack network.
# Expect: 120 MB POST -> 413 from Caddy; small POST -> reaches speech-api (401 without a key).
set -u
cd "$(dirname "$0")/../.."
name=eduvid-caddy-check
docker rm -f $name >/dev/null 2>&1
docker run -d --rm --name $name --network eduvid -e DOMAIN=:8080 \
  -v "$PWD/infra/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.8 >/dev/null
sleep 2
big=$(docker run --rm --network eduvid --entrypoint sh curlimages/curl:8.11.1 -c \
  "head -c 125829120 /dev/zero > /tmp/big && curl -s -o /dev/null -w '%{http_code}' -m 120 -X POST \
   -H 'Content-Type: application/octet-stream' --data-binary @/tmp/big http://$name:8080/speech/v1/audio/transcriptions")
small=$(docker run --rm --network eduvid curlimages/curl:8.11.1 -s -o /dev/null -w '%{http_code}' \
  -X POST -F file=@/etc/hostname "http://$name:8080/speech/v1/audio/transcriptions")
docker rm -f $name >/dev/null 2>&1
echo "120 MB upload -> $big (want 413); small upload -> $small (want 401)"
[ "$big" = 413 ] && [ "$small" = 401 ]
