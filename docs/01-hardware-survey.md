# 01 — Levantamento de hardware

Sistema: Fedora 44, kernel 7.2.5-200.fc44.x86_64, driver `xe`.

## A placa

```
04:00.0 VGA compatible controller [0300]: Intel Corporation Battlemage G21 [Arc B580] [8086:e20b]
	Subsystem: Device [207e:a002]          <- 207e = ONIX Technology
	Kernel driver in use: xe
05:00.0 Audio device [0403]: Intel Corporation Device [8086:e2f7]
	Subsystem: Device [207e:a002]
```

O PCI ID `207e:a002` é o identificador da variante Onix Lumi — é por ele que o driver
do OpenRGB deve reconhecer a placa.

## Onde o LED **não** está

**Não é USB.** `lsusb` não mostra nenhum dispositivo atrás da placa. Os únicos HIDs são
periféricos e o `0b05:19af ASUSTek AURA LED Controller`, que é da **placa-mãe**.
Isso descarta o padrão mais comum de GPU com RGB (MCU USB interno, tipo ASUS/MSI).

**Não é o SMBus da placa-mãe.** Varredura do `i2c-16` (`SMBus I801 adapter at 0000:80:1f.4`):

```
50: -- UU -- UU -- -- -- --  ...
```

Só os SPDs dos módulos de memória (`UU` = reivindicados pelo kernel). Nada da GPU.
Isso descarta a rota que o OpenRGB usa para GPUs ASUS/Gigabyte (pinos SMBus do slot PCIe).

## Onde o LED **está**

A GPU expõe 10 barramentos I²C próprios:

| bus | nome | papel |
|---|---|---|
| i2c-3..i2c-11 | `i915 gmbus dpa..tc4` | DDC dos conectores de vídeo |
| **i2c-15** | **`Synopsys DesignWare I2C adapter`** | **barramento interno da placa** |
| i2c-16 | `SMBus I801` | placa-mãe (não é da GPU) |

O `i2c-15` é um controlador DesignWare instanciado pelo driver `xe`
(`drivers/gpu/drm/xe/xe_i2c.c`) como `i2c_designware.1024`, filho direto de `0000:04:00.0`.
Não é DDC — é o barramento de serviço da própria placa.

Varredura do i2c-15: **um único dispositivo, em `0x28`.**

```
20: -- -- -- -- -- -- -- -- 28 -- -- -- -- -- -- --
```

E o kernel já sabe o que é:

```
/sys/.../i2c_designware.1024/i2c-15/15-0028/name      -> amc
/sys/.../i2c_designware.1024/i2c-15/15-0028/modalias  -> i2c:amc
/sys/.../i2c_designware.1024/i2c-15/15-0028/driver    -> (não existe)
```

**AMC = Add-in card Management Controller**, o microcontrolador de gerenciamento da
placa. O `xe` o instancia com `I2C_CLIENT_HOST_NOTIFY` e trata alertas SMBus
(`xe_amc_handle_alert`), mas **não liga nenhum driver nele** — o endereço fica livre
para acesso via `/dev/i2c-15` do userspace.

O AMC é também o alvo do *late binding firmware* do `xe` (`xe_late_bind_fw.c`,
atributos `lb_fan_control_version` e `lb_voltage_regulator_version` no sysfs da GPU),
o que confirma que ele controla ventoinha e VRM — e é o candidato natural para o LED.

## Permissões

Não precisa de root. O `systemd-logind` concede ACL `uaccess` ao usuário da sessão local:

```
# file: dev/i2c-15
user:arthur:rw-
```

## Primeira sondagem (somente leitura)

```
SMBus receive byte        -> 0xfe
read byte data 0x00..0x05 -> 0xfe
                    0x06  -> 0x01
                    0x07  -> 0x01
             0x08..0x0e   -> 0xfe
                    0x0f  -> 0x01
```

O dispositivo faz ACK e responde. O padrão `0xfe` dominante com alguns `0x01` sugere
**protocolo de comando/resposta**, não um mapa de registradores plano — provavelmente
`0xFE` é um código de erro ("comando não suportado" / "sem resposta pendente") devolvido
para qualquer leitura que não siga um comando válido.

Nenhum erro de I²C no `dmesg` após as leituras.

## Conclusão

O caminho é: **`/dev/i2c-15`, endereço `0x28`, protocolo do AMC**. O que falta é o
conjunto de comandos — que vem da análise do app Windows (ver `docs/02-*`).

## Risco

O AMC controla ventoinha e VRM. Escrita de comandos desconhecidos pode parar a
refrigeração. Toda escrita deve ser feita com monitoramento de
`/sys/class/hwmon/hwmon*/fan[123]_input` e temperatura em paralelo.
