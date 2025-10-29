import type { Tool } from '@modelcontextprotocol/sdk/types.js'
import { makeSearchKnowledge } from './search_knowledge.js'
import { makeFetchChunk } from './fetch_chunk.js'
import { makeFetchLines } from './fetch_lines.js'
import { makeOpenInEditor } from './open_in_editor.js'
import { makeGetVectorStoreInfo } from './get_vector_store_info.js'
import { makeGetMetadata } from './get_metadata.js'

export const tools: Array<{ definition: Tool; handler: any }> = [
  makeSearchKnowledge(),
  makeFetchChunk(),
  makeFetchLines(),
  makeOpenInEditor(),
  makeGetVectorStoreInfo(),
  makeGetMetadata()
]
