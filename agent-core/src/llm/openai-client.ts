import OpenAI from "openai";

export interface OpenAIClientConfig {
  apiKey?: string;
  baseUrl?: string;
  model: string;
  temperature?: number;
  maxOutputTokens?: number;
}

type OpenAIFactory = (options: { apiKey: string; baseURL?: string }) => OpenAI;

export interface OpenAITextContent {
  type: "text" | "output_text";
  text: string;
}

export interface OpenAIInputMessage {
  role: "user" | "assistant";
  content: Array<{ type: string; [key: string]: unknown }>;
}

export interface OpenAIResponseTool {
  type: "function";
  function: {
    name: string;
    description?: string;
    parameters: Record<string, unknown>;
  };
}

export interface OpenAIResponse {
  id: string;
  model: string;
  status: string;
  output: Array<
    | {
        type: "message";
        role: "assistant";
        content: Array<{ type: string; [key: string]: unknown }>;
      }
    | {
        type: "tool_call";
        call_id: string;
        name: string;
        arguments: string;
      }
  >;
  usage?: {
    input_tokens: number;
    output_tokens: number;
  };
  stop_reason?: string;
}

export class OpenAIClient {
  private readonly config: OpenAIClientConfig;
  private readonly client: OpenAI;

  constructor(config: OpenAIClientConfig, factory?: OpenAIFactory) {
    const apiKey =
      config.apiKey ||
      process.env.DOLPHIN_OPENAI_API_KEY ||
      process.env.OPENAI_API_KEY;

    if (!apiKey) {
      throw new Error("OPENAI_API_KEY is not set");
    }

    const baseURL = config.baseUrl || process.env.DOLPHIN_OPENAI_BASE_URL || process.env.OPENAI_BASE_URL;

    this.config = config;
    const create = factory ?? ((options) => new OpenAI(options));
    this.client = create({ apiKey, baseURL });
  }

  async streamResponse(options: {
    messages: OpenAIInputMessage[];
    tools?: OpenAIResponseTool[];
    signal?: AbortSignal;
    onTextChunk?: (chunk: string) => void;
  }): Promise<OpenAIResponse> {
    const stream = this.client.responses.stream(
      {
        model: this.config.model,
        input: options.messages,
        tools: options.tools,
        temperature: this.config.temperature,
        max_output_tokens: this.config.maxOutputTokens,
      },
      { signal: options.signal }
    );

    for await (const event of stream) {
      if (event.type === "response.output_text.delta" && options.onTextChunk) {
        options.onTextChunk(event.delta);
      }
    }

    const finalResponsePromise = stream.finalResponse() as Promise<unknown>;
    const finalResponse = (await finalResponsePromise) as OpenAIResponse;
    return finalResponse;
  }
}
