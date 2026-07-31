#!/usr/bin/env bash

set -e  # aborta o script se qualquer comando falhar

echo "==> Limpando o caso"
foamCleanCase

echo "==> Gerando malha base (blockMesh)"
blockMesh

echo "==> Extraindo feature edges (surfaceFeatures)"
surfaceFeatures

echo "==> Rodando snappyHexMesh"
snappyHexMesh -overwrite

echo "==> Processo concluído com sucesso"
