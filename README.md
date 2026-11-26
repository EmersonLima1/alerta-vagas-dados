# Alerta de vagas remotas de dados (Telegram / WhatsApp)

Automação em Python, agendada no **GitHub Actions**, que busca vagas
**remotas no Brasil** na área de dados, filtra por cargo e nível e envia
as novidades para o meu celular (Telegram, ou WhatsApp via CallMeBot), sem repetir vagas e sem vagas antigas.

> **Status:** v1 funcionando. 60 testes automatizados; busca real na Gupy e
> envio real pelo Telegram validados em 26/11/2026 (veja [Validação](#validação)).

## Problema

Procurar vagas manualmente todo dia em vários sites é repetitivo e fácil de
esquecer, e vagas boas recebem muitas candidaturas nos primeiros dias.
O objetivo é ser avisado rápido, só com vagas que realmente interessam.

## Escopo da v1

| Critério | Regra |
|---|---|
| Cargos e níveis | Analista de Dados (Jr/Pleno), Analista de BI (Jr/Pleno), Cientista de Dados (Jr), Engenheiro de Dados (Jr) |
| Nível não informado no título | Aceito (é muito comum) e sinalizado na mensagem; configurável |
| Modelo | Somente remoto |
| Localização | Somente Brasil (país vazio é aceito; títulos com "International", "LATAM" etc. são descartados) |
| Idade | Publicada há no máximo **7 dias** |
| Repetição | Cada vaga é enviada uma única vez |
| Frequência | De hora em hora, das 08h às 22h (Brasília) |
| Fonte | Gupy (endpoint JSON do portal público) |

**Fora da v1 (ideias para versões futuras):** outras fontes (LinkedIn não tem
API pública para isso; avaliar Programathor, Remotar e repositórios de vagas no
GitHub), filtro por palavras-chave na descrição (ex.: SQL, Python), resumo
diário, painel com histórico das vagas (ótimo gancho para um projeto de BI).

## Critérios de sucesso

1. Nenhuma vaga sênior, estágio, presencial/híbrida ou internacional chega no celular.
2. Nenhuma vaga chega duas vezes.
3. Nenhuma vaga com mais de 7 dias chega.
4. Se a fonte ou o envio quebrar, eu fico sabendo (o GitHub manda e-mail quando um workflow falha).

## Como funciona

```
GitHub Actions (cron)                      data/vagas_enviadas.json
        │                                        ▲        │
        ▼                                        │        │ (lê: o que já foi enviado)
  ┌───────────┐   ┌────────────┐   ┌─────────────┴──┐     │
  │ Extrair   │──▶│ Transformar │──▶│ Carregar       │◀────┘
  │ API Gupy  │   │ filtros +   │   │ Telegram/Zap + │
  │           │   │ deduplicação│   │ salva estado   │
  └───────────┘   └────────────┘   └────────────────┘
```

É um pequeno ETL: extrai vagas da API, transforma (normaliza, filtra,
remove já enviadas) e carrega (envia e registra).

```
src/alerta_vagas/
├── __main__.py      # orquestra o fluxo; `python -m alerta_vagas [--dry-run]`
├── config.py        # cargos, níveis, idade máxima, limites
├── modelos.py       # Vaga: formato comum a todas as fontes
├── fontes/gupy.py   # busca + paginação + retry + normalização
├── filtros.py       # remota, Brasil, recente, cargo, nível
├── estado.py        # vagas já enviadas (JSON no repo)
└── notificador.py   # formata e envia (Telegram ou CallMeBot)
tests/               # pytest, sem acessar a internet
.github/workflows/
├── alerta-vagas.yml # agendamento + envio + commit do estado
└── testes.yml       # roda os testes a cada push
```

## Decisões técnicas

**Fonte: endpoint JSON do portal da Gupy.** A Gupy concentra boa parte das
vagas de empresas brasileiras. Ela não tem API oficial de busca para
candidatos; o script usa o mesmo endpoint JSON, sem login, que o portal
público chama no navegador (`portal.gupy.io/api/job-search/jobs`). É mais
leve e estável que raspar HTML, mas é interno e não documentado: já mudou de
endereço em outubro de 2026. Por isso o uso é pessoal e moderado (algumas
requisições por hora) e o código falha de forma explícita se o formato
mudar, em vez de parar de enviar vagas em silêncio. Alternativa oficial para
uma v2: a API do Adzuna, que tem vagas do Brasil e exige cadastro gratuito.

**Canal de envio: Telegram agora, WhatsApp quando der.** Comparação feita para uso pessoal:

| | Telegram Bot API | CallMeBot (WhatsApp) | Twilio (WhatsApp) | WhatsApp Cloud API (Meta) |
|---|---|---|---|---|
| Custo | Grátis | Grátis | Pago após crédito de teste | Pode cobrar por mensagem de template |
| Configuração | Criar bot no @BotFather (2 min) | 1 mensagem para receber a apikey | Conta + sandbox, que expira e precisa ser reativado | Conta Meta Business, número, token, template aprovado |
| Mensagem livre | Sim | Sim | Só no sandbox ou com template | Fora da janela de 24h, só com template |
| Oficial / confiável | Sim | Não oficial, sem garantia | Sim | Sim |

O plano era o CallMeBot, o único jeito gratuito e simples de mandar texto
livre para o próprio WhatsApp. Em novembro de 2026 ele estava **sem vagas
para novos usuários**, o que confirmou o risco de depender de um serviço não
oficial. Por isso o Telegram virou o canal padrão: API oficial, gratuita e
sem burocracia. O envio fica isolado em `notificador.py`, com a mesma
interface `enviar(texto)` para os dois canais, e o canal é escolhido pelos
secrets que existirem. Migrar para o WhatsApp depois é só cadastrar os
secrets do CallMeBot e apagar os do Telegram, sem mudar código.

**Estado em arquivo no repositório, não no cache do Actions.** O cache é
apagado após 7 dias sem uso e pode ser despejado a qualquer momento, o que
faria vagas serem reenviadas. O JSON versionado tem histórico (`git log`),
é fácil de inspecionar e de corrigir à mão. Entradas com mais de 60 dias são
removidas para o arquivo não crescer para sempre.

**Só marca como enviada depois do envio dar certo.** Se o WhatsApp falhar na
2ª mensagem, as vagas da 1ª ficam registradas e as da 2ª são tentadas de novo
na próxima execução.

**7 dias de idade máxima.** As vagas costumam ficar abertas por semanas, mas
as primeiras candidaturas têm mais chance. Na prática, como o script roda de
hora em hora, quase tudo chega com menos de 1 dia; os 7 dias servem de margem
caso o workflow fique parado. Ajustável pela variável `MAX_DIAS`.

**De hora em hora, das 08h às 22h.** "Enviar quando encontrar" num sistema
agendado vira "verificar com frequência". Uma hora é rápido o suficiente
para vagas e evita notificações de madrugada. Cada execução deve durar menos de
1 minuto (confirmar nos primeiros logs), bem dentro da cota gratuita do Actions (ilimitada em repositório
público; 2.000 min/mês em privado, e isto usa cerca de 500). O agendamento
do GitHub pode atrasar alguns minutos em horários de pico, por isso usamos o
minuto 17 e não o 0.

**Teto de 20 vagas por execução.** Evita uma enxurrada na primeira execução;
o restante sai nas próximas, mais recentes primeiro.

## Configuração (passo a passo)

### 1. Criar o bot do Telegram (canal padrão)

1. No Telegram, abra uma conversa com **@BotFather** (o perfil oficial, com selo azul).
2. Envie `/newbot`, escolha um nome e um usuário terminado em `bot`
   (ex.: `alerta_vagas_emerson_bot`).
3. O BotFather responde com o **token** do bot (algo como `123456:ABC-...`).
   Trate como senha.
4. Abra a conversa com o seu bot novo e envie qualquer mensagem (ex.: `oi`).
   Sem isso o bot não tem permissão para falar com você.
5. Descubra o seu **chat_id**: abra no navegador
   `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates` e procure
   `"chat":{"id":123456789` na resposta. Esse número é o chat_id.

### 1b. Alternativa: WhatsApp via CallMeBot

1. Abra <https://www.callmebot.com/blog/free-api-whatsapp-messages/> e copie o
   número do bot indicado (se aparecer "The bot is currently full", ainda não há
   vagas; tente outro dia).
2. Salve o número nos contatos e envie a ele pelo WhatsApp:
   `I allow callmebot to send me messages`
3. Você recebe de volta a sua **apikey**.

### 2. Cadastrar os segredos no GitHub

No repositório: **Settings → Secrets and variables → Actions → New repository secret**

| Canal | Nome | Valor |
|---|---|---|
| Telegram | `TELEGRAM_BOT_TOKEN` | O token do BotFather |
| Telegram | `TELEGRAM_CHAT_ID` | O seu chat_id |
| WhatsApp | `WHATSAPP_PHONE` | Seu número com DDI e DDD, ex.: `+5577999999999` |
| WhatsApp | `CALLMEBOT_APIKEY` | A apikey recebida |

Cadastre os de **um** canal. Se os do Telegram existirem, ele tem prioridade.
Secrets ficam criptografados, não aparecem no código e são mascarados nos
logs. Nunca coloque token, número ou chave no código.

### 3. Primeira execução (sem enviar)

**Actions → Alerta de vagas → Run workflow**, com "Só mostrar no log" marcado.
O log mostra as mensagens que seriam enviadas e o resumo do filtro, por exemplo:

```
Resumo do filtro: {'cargo_fora_do_escopo': 180, 'aceita': 12, 'nivel_senior_nao_aceito_para_Analista de Dados': 30, ...}
```

Confira se as vagas aceitas fazem sentido. Depois rode de novo desmarcando a
opção para testar o envio real. A partir daí o agendamento assume.

## Rodando localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                    # testes
PYTHONPATH=src python -m alerta_vagas --dry-run   # busca real, sem enviar
```

Para enviar de verdade localmente, defina no ambiente as mesmas variáveis
dos secrets (`TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`, por exemplo).

## Validação

- [x] Testes unitários: identificação de cargo e nível (incluindo "I/II/III" e
      "BI" não virar nível "I"), filtros de remoto, Brasil e idade, paginação e
      deduplicação da fonte, falha parcial da fonte, falha no meio do envio,
      poda do estado, erro do CallMeBot com HTTP 200, escape de HTML no Telegram,
      escolha do canal pelos secrets, token/apikey nunca aparecem em erro.
- [x] Execução real na Gupy (dry-run no Actions, 26/11/2026). Achou e corrigiu:
      endereço novo da API e rótulo de nível na mensagem.
- [x] Primeiro envio real pelo Telegram (26/11/2026, mensagem recebida)
- [ ] Execuções agendadas disparando sozinhas
- [ ] Uma semana rodando: conferir falsos positivos/negativos e ajustar `config.py`

## Limitações conhecidas

- O filtro de nível usa o **título** da vaga. Vagas sem nível no título são
  aceitas e marcadas como "nível não informado".
- A API da Gupy não é oficial e pode mudar.
- O GitHub desativa workflows agendados em repositórios públicos sem
  atividade por 60 dias (o próprio commit do estado conta como atividade
  quando há vagas novas, mas vale ficar atento ao e-mail de aviso).
