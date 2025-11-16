import OpenAI from "openai";

export interface OpenAIClientConfig {
  apiKey?: string;
  model: string;
  temperature?: number;
  maxOutputTokens?: number;
}

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

  constructor(config: OpenAIClientConfig) {
    if (!config.apiKey && !process.env.OPENAI_API_KEY) {
      throw new Error("OPENAI_API_KEY is not set");
    }

    this.config = config;
    this.client = new OpenAI({ apiKey: config.apiKey || process.env.OPENAI_API_KEY });
  }

  async streamResponse(options: {
    messages: OpenAIInputMessage[];
    tools?: OpenAIResponseTool[];
    signal?: AbortSignal;
    onTextChunk?: (chunk: string) => void;
  }): Promise<OpenAIResponse> {
    const stream = await this.client.responses.stream(
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

    const finalResponse = (await stream.finalResponse()) as OpenAIResponse;
    return finalResponse;
  }
}
