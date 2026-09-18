# 03 — Armadilhas (aprendidas na prática)

## Leitura I²C crua *fora de contexto* trava o AMC até o próximo boot

**O que aconteceu.** Depois de um `i2cdetect` e leituras `read_byte_data` bem-sucedidas,
foi feita uma leitura I²C crua — `I2C_RDWR` com uma única mensagem `I2C_M_RD`, sem nenhuma
requisição pendente:

```python
bus.raw_read(0x28, 8)   # -> OSError errno 110 (ETIMEDOUT)
```

A partir daí **todo** acesso ao `0x28` passou a dar timeout, e um novo `i2cdetect -y -r 15`
mostrou o barramento vazio. Não recuperou sozinho em 30 s. Nenhum erro no `dmesg`.

**Por quê.** A leitura crua em si é legítima — é exatamente o que o driver do kernel faz
(`i2c_master_recv`, ver `docs/02-protocolo-amc.md`). O erro foi o **contexto**: o AMC é um
endpoint MCTP, e só tem resposta para entregar depois de receber uma requisição bem
formada e esperar 20 ms. Pedir bytes a um endpoint sem nada na fila o deixou preso no meio
de uma transação, segurando SDA. Com SDA em nível baixo o barramento inteiro morre — não é
o controlador DesignWare que quebrou, é o escravo que não solta a linha.

**Como recuperar.** `tools/recover-bus.sh` (precisa de root) tenta, em ordem: forçar
runtime PM `on`, depois unbind/rebind do driver `i2c_designware`. Se o AMC estiver mesmo
segurando SDA, nada em userspace resolve — só ciclo de energia (reboot).

**Regra.** Leitura crua só imediatamente depois de uma requisição MCTP e do delay de 20 ms.
Use `tools/amc-mctp.py`, que faz o par requisição/resposta junto. O `raw_read()` solto
continua no código apenas como documentação e exige `i_know_the_risk=True`.

## O controlador I²C entra em runtime suspend

`/sys/.../i2c_designware.1024/power/runtime_status` fica `suspended` quando ocioso.
Isso é normal e o driver resume sozinho na transferência — não confunda com o barramento
travado. Para diagnosticar, o sintoma que importa é o `i2cdetect` voltar vazio.

## O AMC não é um mapa de registradores plano

Varredura de `0x00..0xff` com `read_byte_data` devolveu quase tudo `0xfe`, com `0x01` em
`0x06`, `0x07` e `0x0f`. Numa segunda rodada, o *receive byte* devolveu `0x01` onde antes
devolvia `0xfe` — ou seja, **a resposta depende do estado**, não do endereço lido.

Explicação confirmada em `docs/02-protocolo-amc.md`: **não existem registradores**. O AMC
é um endpoint MCTP. O que o `read_byte_data` estava fazendo era escrever um byte (o
"registrador") e ler um byte de volta — ou seja, mandando pacotes MCTP truncados e lendo
respostas inexistentes. `0xFE`/`0x01` é ruído, não dado.

## O AMC controla ventoinha e VRM

Confirmado pelos atributos de *late binding firmware* do driver `xe` no sysfs da GPU
(`lb_fan_control_version`, `lb_voltage_regulator_version`). Comandos de escrita
desconhecidos podem parar a refrigeração. Qualquer teste de escrita tem que rodar com
`fan*_input` e `temp*_input` monitorados em paralelo.
