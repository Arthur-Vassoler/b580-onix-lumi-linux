#!/usr/bin/env bash
# Recupera o barramento I2C interno da GPU quando o AMC para de responder.
# Precisa de root. Vai do menos para o mais invasivo e testa depois de cada passo.
set -uo pipefail

DEV=i2c_designware.1024
DRV=/sys/bus/platform/drivers/i2c_designware
SYSDEV=/sys/bus/platform/devices/$DEV

[ "$(id -u)" -eq 0 ] || { echo "rode como root: sudo $0"; exit 1; }

amc_bus() {
    for c in /sys/bus/i2c/devices/*-0028; do
        [ -e "$c/name" ] && [ "$(cat "$c/name")" = amc ] && { basename "$c" | cut -d- -f1; return; }
    done
}

test_amc() {
    local b; b=$(amc_bus)
    [ -n "$b" ] || { echo "  (client amc não encontrado)"; return 1; }
    if timeout 5 i2cget -y "$b" 0x28 >/dev/null 2>&1; then
        echo "  ✔ AMC responde em /dev/i2c-$b"; return 0
    fi
    echo "  ✘ AMC não responde em /dev/i2c-$b"; return 1
}

echo "estado inicial:"; test_amc && { echo "nada a fazer."; exit 0; }

echo
echo "[1/3] forçando runtime PM 'on' no controlador..."
echo on > "$SYSDEV/power/control" 2>/dev/null
sleep 1
test_amc && exit 0

echo
echo "[2/3] unbind/rebind do driver i2c_designware (reinicializa o controlador)..."
echo "$DEV" > "$DRV/unbind" 2>/dev/null
sleep 1
echo "$DEV" > "$DRV/bind" 2>/dev/null
sleep 2
test_amc && exit 0

echo
echo "[3/3] nenhum passo em userspace resolveu."
echo
echo "Provavelmente o próprio AMC está segurando o barramento (SDA preso em nível baixo)."
echo "Só um ciclo de energia da placa resolve: reinicie a máquina."
echo "Um 'reboot' quente costuma bastar; se não, desligue de vez e ligue de novo."
exit 1
