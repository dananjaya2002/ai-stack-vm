# Ports Used

| Service           | Port  | Notes                              |
|-------------------|-------|------------------------------------|
| Open WebUI        | 8080  | Browser chat UI                    |
| laptop-llama      | 8081  | Laptop GPU model (qwen2.5-coder-3B)|
| vm-llama          | 8082  | VM CPU model (qwen2.5-coder-7B)    |
| Qdrant REST       | 6333  | Vector database                    |
| Qdrant gRPC       | 6334  | Vector database (gRPC)             |
| code-proxy        | 9001  | Code-RAG OpenAI-compatible proxy   |
| memory-proxy      | 9002  | Memory-RAG OpenAI-compatible proxy |
