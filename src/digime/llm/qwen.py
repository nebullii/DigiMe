class QwenClient:
    """Adapter for local Qwen-compatible runtimes such as Ollama or llama.cpp."""

    def generate(self, prompt: str) -> str:
        raise NotImplementedError("Connect this to the selected local runtime.")

