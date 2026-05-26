import {
  workflow,
  node,
  trigger,
  sticky,
  placeholder,
  newCredential,
  languageModel,
  tool,
  expr,
} from "@n8n/workflow-sdk";

const incomingWhatsApp = trigger({
  type: "n8n-nodes-base.webhook",
  version: 2.1,
  config: {
    name: "Entrada WhatsApp",
    parameters: {
      httpMethod: "POST",
      path: "garmin-whatsapp-assistant",
      authentication: "none",
      responseMode: "responseNode",
      options: {
        ignoreBots: true,
        responseHeaders: {
          entries: [{ name: "Content-Type", value: "application/json" }],
        },
      },
    },
    position: [240, 300],
  },
  output: [
    {
      headers: {},
      params: {},
      query: {},
      body: {
        event: "messages.upsert",
        data: {
          key: {
            remoteJid: "5511999999999@s.whatsapp.net",
            id: "sample-message-id",
            fromMe: false,
          },
          message: { conversation: "Como foi meu sono hoje?" },
        },
      },
    },
  ],
});

const extractWhatsAppMessage = node({
  type: "n8n-nodes-base.code",
  version: 2,
  config: {
    name: "Extrair mensagem do WhatsApp",
    parameters: {
      mode: "runOnceForAllItems",
      language: "javaScript",
      jsCode: `const item = $input.first();
const root = item.json || {};
const body = root.body || root;
const data = body.data || body;
const key = data.key || {};
const message = data.message || body.message || {};
const cloudChange = body.entry?.[0]?.changes?.[0]?.value;
const cloudMessage = cloudChange?.messages?.[0];
const remoteJid = key.remoteJid || data.remoteJid || body.remoteJid || cloudMessage?.from || body.from || root.from || "";
const rawPhone = remoteJid || cloudMessage?.from || body.phone || body.number || "";
const phone = String(rawPhone).replace("@s.whatsapp.net", "").replace("@c.us", "").replace(/\\D/g, "");
const text = message.conversation
  || message.extendedTextMessage?.text
  || message.imageMessage?.caption
  || cloudMessage?.text?.body
  || body.text
  || body.messageText
  || body.message
  || root.text
  || "";
const mediaUrl = message.imageMessage?.url
  || cloudMessage?.image?.link
  || body.mediaUrl
  || body.imageUrl
  || "";
const mimeType = message.imageMessage?.mimetype
  || cloudMessage?.image?.mime_type
  || body.mimeType
  || "";
return [{
  json: {
    channel: "whatsapp",
    from: remoteJid,
    remoteJid,
    phone,
    messageText: String(text).trim(),
    messageId: key.id || cloudMessage?.id || body.messageId || "",
    fromMe: Boolean(key.fromMe || body.fromMe),
    hasImage: Boolean(mediaUrl || mimeType.startsWith("image/")),
    mediaUrl,
    mimeType,
    receivedAt: new Date().toISOString(),
    raw: body
  }
}];`,
    },
    position: [520, 300],
  },
  output: [
    {
      channel: "whatsapp",
      from: "5511999999999@s.whatsapp.net",
      remoteJid: "5511999999999@s.whatsapp.net",
      phone: "5511999999999",
      messageText: "Como foi meu sono hoje?",
      messageId: "sample-message-id",
      fromMe: false,
      hasImage: false,
      mediaUrl: "",
      mimeType: "",
      receivedAt: "2026-05-26T12:00:00.000Z",
      raw: {},
    },
  ],
});

const checkGarminLogin = node({
  type: "n8n-nodes-base.httpRequest",
  version: 4.4,
  config: {
    name: "Verificar login Garmin",
    parameters: {
      method: "GET",
      url: "http://167.86.116.131:8001/me",
      authentication: "genericCredentialType",
      genericAuthType: "httpHeaderAuth",
      sendHeaders: true,
      specifyHeaders: "keypair",
      headerParameters: {
        parameters: [{ name: "Accept", value: "application/json" }],
      },
      options: {
        response: {
          response: {
            fullResponse: true,
            neverError: true,
            responseFormat: "json",
          },
        },
        timeout: 15000,
      },
    },
    credentials: {
      httpHeaderAuth: newCredential("Garmin API Key - header X-API-Key"),
    },
    position: [800, 300],
  },
  output: [
    {
      statusCode: 200,
      headers: {},
      body: { id: "default", email: "voce@example.com", display_name: "Samuel" },
    },
  ],
});

const openAiModel = languageModel({
  type: "@n8n/n8n-nodes-langchain.lmChatOpenAi",
  version: 1.3,
  config: {
    name: "Modelo OpenAI",
    parameters: {
      model: { __rl: true, mode: "id", value: "gpt-5-mini" },
      responsesApiEnabled: true,
      options: {
        reasoningEffort: "low",
        temperature: 0.2,
        maxRetries: 2,
        timeout: 90000,
      },
    },
    credentials: { openAiApi: newCredential("OpenAI") },
    position: [1060, 580],
  },
});

const garminMcpTools = tool({
  type: "@n8n/n8n-nodes-langchain.mcpClientTool",
  version: 1.2,
  config: {
    name: "Garmin MCP",
    parameters: {
      endpointUrl: placeholder(
        "Endpoint Streamable HTTP do Garmin MCP. Exemplo: https://garmin-mcp.seudominio.com/mcp",
      ),
      serverTransport: "httpStreamable",
      authentication: "bearerAuth",
      include: "selected",
      includeTools: [
        "build_garmin_context",
        "get_daily_report",
        "call_garmin_route",
        "search_garmin_docs",
        "get_route_contract",
      ],
      options: { timeout: 120000 },
    },
    credentials: { httpBearerAuth: newCredential("Garmin MCP Bearer Token") },
    position: [1280, 580],
  },
});

const garminAgent = node({
  type: "@n8n/n8n-nodes-langchain.agent",
  version: 3.1,
  config: {
    name: "Agente Garmin",
    parameters: {
      promptType: "define",
      text: expr(
        'Mensagem do WhatsApp: {{ $("Extrair mensagem do WhatsApp").item.json.messageText }}\n' +
          'Telefone/remetente: {{ $("Extrair mensagem do WhatsApp").item.json.phone || $("Extrair mensagem do WhatsApp").item.json.remoteJid }}\n' +
          'Tem imagem: {{ $("Extrair mensagem do WhatsApp").item.json.hasImage }}\n' +
          'URL da imagem, se houver: {{ $("Extrair mensagem do WhatsApp").item.json.mediaUrl }}\n' +
          "Status da verificacao Garmin: {{ $json.statusCode || 0 }}\n" +
          "Body da verificacao Garmin: {{ JSON.stringify($json.body || $json) }}\n" +
          "Data/hora atual: {{ $now.toISO() }}",
      ),
      options: {
        systemMessage:
          'Voce e um assistente pessoal de saude conectado ao Garmin Connect via MCP. Responda sempre em portugues do Brasil, em tom direto e util, como mensagem de WhatsApp. Primeiro avalie o resultado do node "Verificar login Garmin". Se o status nao for 2xx, ou se a conta nao parecer autenticada, responda que eu ainda nao estou logado no Garmin e diga para autenticar/cadastrar a conta na Garmin API antes de pedir metricas; nesse caso nao chame ferramentas do Garmin MCP. Se estiver logado, use as ferramentas do node "Garmin MCP" para buscar dados reais. Comece com build_garmin_context usando a pergunta e a data atual; use get_daily_report para perguntas amplas do dia; use search_garmin_docs e call_garmin_route quando precisar de uma rota especifica. Para pedidos de alimentacao, calorias ou fotos de comida, procure/consulte as rotas de nutrition e photo analysis se houver imagem. Nunca invente metricas, nunca exponha chaves, tokens, emails sensiveis ou payloads brutos. Se um dado nao vier da Garmin, diga que nao encontrou. Responda curto, com numeros e unidades quando existirem.',
        maxIterations: 8,
        returnIntermediateSteps: false,
        passthroughBinaryImages: true,
      },
    },
    subnodes: { model: openAiModel, tools: [garminMcpTools] },
    position: [1080, 300],
  },
  output: [
    {
      output:
        "Seu sono hoje foi de 7h42, com Body Battery subindo para 82. A FC de repouso ficou em 52 bpm.",
    },
  ],
});

const sendWhatsAppReply = node({
  type: "n8n-nodes-base.httpRequest",
  version: 4.4,
  config: {
    name: "Responder no WhatsApp",
    parameters: {
      method: "POST",
      url: placeholder(
        "URL Evolution API sendText. Exemplo: https://evolution.seudominio.com/message/sendText/NOME_DA_INSTANCIA",
      ),
      authentication: "genericCredentialType",
      genericAuthType: "httpHeaderAuth",
      sendBody: true,
      contentType: "json",
      specifyBody: "json",
      jsonBody: expr(
        '{{ { number: $("Extrair mensagem do WhatsApp").item.json.phone || $("Extrair mensagem do WhatsApp").item.json.remoteJid, text: $json.output || "Nao consegui montar a resposta agora." } }}',
      ),
      options: {
        response: {
          response: {
            fullResponse: true,
            neverError: true,
            responseFormat: "json",
          },
        },
        timeout: 20000,
      },
    },
    credentials: { httpHeaderAuth: newCredential("Evolution API Key - header apikey") },
    position: [1360, 300],
  },
  output: [{ statusCode: 200, body: { key: { id: "sample-whatsapp-response" } } }],
});

const respondWebhook = node({
  type: "n8n-nodes-base.respondToWebhook",
  version: 1.5,
  config: {
    name: "Confirmar recebimento",
    parameters: {
      respondWith: "json",
      responseBody: expr(
        '{{ { ok: true, answer: $("Agente Garmin").item.json.output, whatsappStatus: $json.statusCode || 200 } }}',
      ),
      options: {
        responseCode: 200,
        responseHeaders: {
          entries: [{ name: "Content-Type", value: "application/json" }],
        },
        enableStreaming: false,
      },
    },
    position: [1640, 300],
  },
  output: [{ ok: true, answer: "Resposta enviada no WhatsApp.", whatsappStatus: 200 }],
});

const setupNote = sticky(
  "## Configurar antes de ativar\n" +
    "1. Credencial **Garmin API Key - header X-API-Key**: header `X-API-Key` com a API key da conta Garmin.\n" +
    "2. URL do node **Verificar login Garmin** apontando para `/accounts/me`.\n" +
    "3. Publicar o Garmin MCP em Streamable HTTP e preencher o endpoint no tool **Garmin MCP**.\n" +
    "4. Credencial **Garmin MCP Bearer Token** se o MCP estiver protegido.\n" +
    "5. Credencial **OpenAI**.\n" +
    "6. Credencial **Evolution API Key - header apikey** e URL `/message/sendText/{instancia}` no node de resposta.\n" +
    "7. Configure o webhook da Evolution/WhatsApp para chamar o webhook de producao deste workflow.",
  [incomingWhatsApp, checkGarminLogin, garminAgent, sendWhatsAppReply],
  { color: 5 },
);

export default workflow("garmin-whatsapp-assistant", "Garmin WhatsApp Assistant")
  .add(setupNote)
  .add(incomingWhatsApp)
  .to(extractWhatsAppMessage)
  .to(checkGarminLogin)
  .to(garminAgent)
  .to(sendWhatsAppReply)
  .to(respondWebhook);
