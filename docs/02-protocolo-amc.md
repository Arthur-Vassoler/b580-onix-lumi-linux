# 02 — O protocolo do AMC

Fonte primária: `drivers/gpu/drm/xe/xe_amc.c` no kernel Linux (Copyright 2026 Intel).
Não é engenharia reversa — é o próprio driver da Intel, com o formato de pacote explícito.

## O AMC fala MCTP sobre SMBus

Não é mapa de registradores. É **MCTP** (DMTF DSP0236) transportado sobre SMBus
(DSP0237), com o corpo da mensagem sendo **Vendor Defined – PCI** (tipo `0x7E`) da Intel.

Por isso a varredura de registradores só devolvia `0xfe`: não existe registrador nenhum.

## Formato da requisição

```c
struct amc_header {          /* 7 bytes */
    u8 command;              /* 0x0F — command code de MCTP sobre SMBus  */
    u8 len;                  /* byte count: total do pacote menos 2      */
    u8 address;              /* 0x8F — endereço de origem (o host)       */
    u8 version;              /* 0x01 — versão do cabeçalho MCTP          */
    u8 destination;          /* 12   — EID de destino (o AMC)            */
    u8 source;               /* 8    — EID de origem (o host)            */
    u8 flags;                /* 0xC8 — SOM|EOM|TO, seq 0, tag 0          */
};

struct amc_message {         /* 4 bytes */
    u8  type;                /* 0x7E — Vendor Defined PCI                */
    u16 vendor;              /* 0x8086 big-endian (Intel)                */
    u8  command;             /* comando específico do vendor             */
};

struct amc_request  { amc_header; amc_message; u32 reserved; };   /* 15 bytes */
struct amc_response { amc_header; amc_message; u8 error; u8 value; }; /* 13 bytes */
```

`flags = 0xC8` decompõe em SOM=1, EOM=1, seq=0, TO=1, tag=0 — pacote único,
esperando resposta. MCTP de manual.

`len = sizeof(request) - 2 = 13`: conta tudo depois do próprio byte de contagem
(5 bytes de cabeçalho + 4 da mensagem + 4 reservados).

## Como a transação acontece

```c
i2c_master_send(client, request, 15);   /* escrita I2C crua, 15 bytes      */
fsleep(20 * USEC_PER_MSEC);             /* o AMC precisa de 20 ms          */
i2c_master_recv(client, response, 13);  /* leitura I2C crua, 13 bytes      */
```

Três detalhes que importam:

1. **Não é transação SMBus do i2c-dev.** É escrita crua seguida de leitura crua, com
   `0x0F` como primeiro byte do payload — não como byte de comando SMBus.
2. **Os 20 ms não são opcionais.** Ler antes disso devolve lixo ou nada.
3. **Sem PEC.** O cliente não é criado com `I2C_CLIENT_PEC`.

O driver valida a resposta comparando `response.message` com `request.message` byte a
byte — ou seja, o AMC ecoa tipo/vendor/comando. Bom canário para saber se um comando
foi aceito.

## O único comando conhecido

```c
#define AMC_MSG_TYPE         0x7e
#define AMC_GET_ALERT_REASON 0x01
```

`error` != 0 na resposta significa comando rejeitado. `value` traz o motivo do alerta:

| valor | significado |
|---|---|
| 0 | desconhecido |
| 1 | Firmware Download |
| 2 | Thermal Trip |
| 3 | OOB Request |
| 4 | OOB Reset |
| 5 | Catastrophic |

## Por que isso destrava o projeto

O espaço de busca deixou de ser "256 registradores opacos" e virou "o byte `command`
dentro de uma mensagem vendor-defined bem formada". E, melhor: MCTP tem **descoberta
padronizada**. Mensagens de controle (tipo `0x00`) incluem:

| cmd | o que faz |
|---|---|
| 0x02 | Get Endpoint ID |
| 0x03 | Get Endpoint UUID |
| 0x04 | Get MCTP Version Support |
| 0x05 | Get Message Type Support |
| 0x06 | **Get Vendor Defined Message Support** |

O `0x06` devolve **quais vendor IDs o endpoint atende**. Se a Onix pendurou o controle
de LED num vendor-defined próprio (PCI vendor `0x207E`) em vez do da Intel, esse comando
mostra. Tudo isso é leitura, definido por norma, e sem efeito colateral.

## Hipóteses para o LED

1. Vendor-defined Intel (`0x8086`) com um `command` ainda não catalogado.
2. Vendor-defined Onix (`0x207E`) — o `Get Vendor Defined Message Support` resolve.
3. O LED não está no AMC e existe um segundo MCU atrás dele. Menos provável: a varredura
   do `i2c-15` achou só o `0x28`.

A ordem de ataque é: descoberta MCTP primeiro (barata e segura), análise do app Windows
em paralelo, e só então varredura do espaço de comandos.

## Importante: MCTP não é o canal do LED

Este documento descreve o canal de **alerta** que o driver `xe` usa. A análise do app
Windows (`docs/04-app-windows.md`) mostrou que o LED usa outra coisa no mesmo endereço:
escrita direta de pares `(registrador, valor)`, sem framing MCTP nenhum
(`docs/05-protocolo-led.md`).

Os dois convivem em `0x28`. Note que o command code de MCTP sobre SMBus é `0x0F`, que
é também o registrador de *bypass* do LED — uma colisão aparente que ainda não foi
investigada. Na dúvida, prefira mandar o `0x0F` acompanhado do seu valor, como o app faz.

## Referências

- `drivers/gpu/drm/xe/xe_amc.c`, `xe_i2c.c`, `xe_i2c.h` — kernel Linux
- DMTF DSP0236 — MCTP Base Specification
- DMTF DSP0237 — MCTP SMBus/I2C Transport Binding
