from digime.llm.ollama import OllamaClient


class QwenClient(OllamaClient):
    """Adapter for local Qwen-compatible runtimes such as Ollama or llama.cpp."""
