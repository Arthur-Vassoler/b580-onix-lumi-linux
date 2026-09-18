# 05 — O protocolo do LED (completo)

Extraído do IL de `Onix.Controller.LightingController` em `LUMI.exe` v1.0.0.0,
com `tools/dotnet-il.py`. Não é hipótese: são os bytes que o app oficial escreve.

## Forma da transação

```
escreve N bytes em 0x28   →   lê 1 byte
```

A assinatura do P/Invoke, deduzida da pilha do IL:

```csharp
WriteReadAsync(byte[] writeBuf, int writeLen, byte[] readBuf, int readLen,
               IoCompleteCallback callback)
```

Todos os chamadores passam `readBuf = new byte[1]`. O byte lido é descartado pelo app.
Medido no hardware: é **eco do último valor escrito**, não um status.

**O payload é uma sequência de pares `(registrador, valor)`.** Vários pares podem ir
numa única escrita — mas **nunca junto com uma troca de modo**: agrupar `0x10` com cor
e brilho faz o LED apagar, mesmo com o comando sendo aceito. Confirmado no hardware,
ver `docs/06-validacao-hardware.md`. A init agrupa três pares, e ali não há troca de modo.

Nada de MCTP aqui. O framing MCTP de `docs/02-protocolo-amc.md` é o canal de *alerta*
que o kernel usa no mesmo endereço; o LED usa escrita de registrador direta.

## Mapa de registradores

| reg | função | valores |
|---:|---|---|
| `0x0F` | bypass | 0 = desligado, 1 = ligado |
| `0x10` | **modo** | ver tabela abaixo |
| `0x11` | Runway: **response** | padrão 10 — obrigatório, ver abaixo |
| `0x12` | Runway: interval | padrão 1 |
| `0x13` | OneColor: **response** | padrão 10 — obrigatório |
| `0x14` | direção | argumento de `LedDirection` |
| `0x16` | Serial: **response** | padrão 2 — obrigatório |
| `0x17` | Serial: speed | padrão 16 |
| `0x18` | Rainbow: **response** | padrão 2 — obrigatório |
| `0x19` | Rainbow: speed | padrão 5 |
| `0x1A` | Custom: **R** | 0–255 |
| `0x1B` | Custom: **G** | 0–255 |
| `0x1C` | Custom: **B** | 0–255 |
| `0x20` | BlockStacking: speed | padrão 10 |
| `0x27` | — | só aparece na init, sempre `0x0E` |
| `0x29` | Runway: chaser | padrão 1 |
| `0x3E` | **brilho** | padrão `0x88` (136) |
| `0xC8` | Breathing: tempo | padrão 6 |
| `0xC9` | Breathing: **R** | 0–255 |
| `0xCA` | Breathing: **G** | 0–255 |
| `0xCB` | Breathing: **B** | 0–255 |

## Modos (registrador `0x10`)

| valor | método no app | efeito |
|---:|---|---|
| `0x00` | `SetLedRainbowMode` | Rainbow |
| `0x01` | `SetLedCustomMode` | Custom — cor fixa via `0x1A`–`0x1C` |
| `0x02` | `SetLedBreathingMode` | Breathing — cor via `0xC9`–`0xCB` |
| `0x03` | `SetLedSerialMode` | Serial |
| `0x04` | `SetLedRunwayMode` | Runway |
| `0x05` | `SetLedOneColorMode` | One Color |
| `0x06` | `SetLedBlockStackingMode` | Block Stacking |

> Cuidado: o enum `LightingMode` do código é a ordem do **combobox da interface**
> (Rainbow=0, Runway=1, OneColor=2, Seria=3, Customize=4, BreathingLight=5,
> BlockStacking=6) e **não** coincide com o valor no fio. Só a tabela acima vale.

## O registrador "response" não é opcional

Cada modo animado tem, além da velocidade, um registrador chamado *response* no app
(`0x11` Runway, `0x13` One Color, `0x16` Serial, `0x18` Rainbow). Medido no hardware:
**sem ele, o modo acende mas não anima.** Selecionar Rainbow e escrever só modo, brilho
e velocidade dá um arco-íris congelado; escrever `0x18 = 0x02` põe tudo em movimento.

O que exatamente ele faz continua sem explicação — só que precisa estar escrito. Tanto
o driver quanto `tools/lumi-led.py` mandam sempre o conjunto completo de parâmetros ao
trocar de modo, com os padrões do fabricante.

A velocidade, essa sim, foi confirmada: `0x19` muda visivelmente o ritmo do arco-íris
entre 1 e 40.

## Sequência de inicialização

`<InitializeAsync>d__29::MoveNext` monta um array de 6 bytes a partir de um
inicializador estático `3E 00 0F 00 27 0E` e sobrescreve os índices 1 e 3:

```
[0x3E, brilho, 0x0F, bypass, 0x27, 0x0E]

brilho = 0x88  se o LED está habilitado no ledmode_config.json, senão 0x00
bypass = 0x01  se habilitado no bypass_config.json, senão 0x00
```

Ou seja: **desligar o LED é escrever brilho 0** (`0x3E 0x00`). Não há registrador
separado de liga/desliga.

O app guarda o estado em `ledmode_config.json` e `bypass_config.json` ao lado do
executável — não há persistência no firmware pelo que se vê aqui.

## Padrões de fábrica

Todos os modos nascem com brilho `0x88` (136 de 255). Além disso:

```
Rainbow:       response 2,  speed 5
Runway:        response 10, interval 1, chaser 1
OneColor:      speed 10
Serial:        response 2,  speed 16
BlockStacking: speed 10
Breathing:     tempo 6
```

## Como isso mapeia no OpenRGB

A placa **não tem modo direto por LED**: todos os efeitos são gerados no firmware.
O driver deve expor:

- **Static** → modo `0x01` + cor em `0x1A`/`0x1B`/`0x1C`, com brilho em `0x3E`
- **Breathing** → modo `0x02` + cor em `0xC9`/`0xCA`/`0xCB` + tempo em `0xC8`
- **Rainbow, Serial, Runway, One Color, Block Stacking** → modos sem cor, com os
  respectivos parâmetros de velocidade

Uma zona única, cor global. `MODE_COLORS_MODE_SPECIFIC` para Static e Breathing,
`MODE_COLORS_NONE` para os demais.

## O que ainda não se sabe

- O significado exato de "response" (`0x11`, `0x13`, `0x16`, `0x18`) e os intervalos
  válidos de cada parâmetro. Os padrões estão acima; os limites dos sliders estão no
  BAML dentro de `.rsrc` e ainda não foram extraídos.
- O que `0x27 = 0x0E` faz. Aparece só na init, sempre com o mesmo valor.
- Quantos LEDs a placa tem, e se algum modo aceita endereçamento individual.
