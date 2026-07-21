# llm_client.py
import os
from dotenv import load_dotenv
from typing import Generator, Union, Dict, Any

load_dotenv()


def get_client(provider="kimi"):
    """
    Get LLM client for specified provider.

    Args:
        provider: 'kimi', 'openai', or 'claude'

    Returns:
        Tuple of (client, model, protocol)
        protocol is 'openai-compatible' or 'anthropic'
    """

    if provider == "kimi":
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("KIMI_API_KEY"),
            base_url=os.getenv("KIMI_BASE_URL")
        )
        model = os.getenv("KIMI_MODEL", "kimi-k2.6")
        return client, model, "openai-compatible"

    elif provider == "openai":
        from openai import OpenAI
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        )
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        return client, model, "openai-compatible"

    elif provider == "claude":
        try:
            from anthropic import Anthropic
        except ImportError:
            raise ImportError(
                "The 'anthropic' package is required for Claude support. "
                "Install it with: pip install anthropic"
            )
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        return client, model, "anthropic"

    else:
        raise ValueError(f"Unknown provider: {provider}. Supported: 'kimi', 'openai', 'claude'")


def _convert_messages_for_claude(messages):
    """
    Convert OpenAI-compatible messages (with image_url) to Anthropic format.
    Anthropic expects image blocks with base64 source, not image_url.
    """
    converted = []
    for msg in messages:
        if isinstance(msg.get("content"), list):
            new_content = []
            for part in msg["content"]:
                if part.get("type") == "image_url":
                    url = part["image_url"]["url"]
                    if url.startswith("data:image"):
                        media_type = url.split(";")[0].split(":")[1]
                        base64_data = url.split(",")[1]
                        new_content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_data
                            }
                        })
                    else:
                        new_content.append({
                            "type": "text",
                            "text": f"[Image: {url}]"
                        })
                elif part.get("type") == "text":
                    new_content.append(part)
                else:
                    new_content.append(part)
            converted.append({"role": msg["role"], "content": new_content})
        else:
            converted.append(msg)
    return converted


def _generate_streaming(
    messages,
    provider="kimi",
    system=None,
    temperature=1.0,
    max_tokens=4096
) -> Generator[str, None, None]:
    """Streaming generator — internal use only."""
    client, model, protocol = get_client(provider)

    if protocol == "openai-compatible":
        api_messages = list(messages)
        if system:
            api_messages = [{"role": "system", "content": system}] + api_messages

        response = client.chat.completions.create(
            model=model,
            messages=api_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                yield content

    elif protocol == "anthropic":
        api_messages = _convert_messages_for_claude(messages)
        kwargs = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if system:
            kwargs["system"] = system

        with client.messages.stream(**kwargs) as stream_obj:
            for text in stream_obj.text_stream:
                yield text


def generate(
    messages,
    provider="kimi",
    system=None,
    temperature=1.0,
    max_tokens=4096,
    stream=False
) -> Union[str, Generator[str, None, None]]:
    """
    Unified generate interface across all LLM providers.
    Returns text only for backward compatibility with app.py.
    For benchmark accuracy, use generate_with_metadata().

    Args:
        messages: List of dicts with 'role' and 'content' keys
        provider: 'kimi', 'openai', or 'claude'
        system: Optional system prompt string
        temperature: Sampling temperature (0-1)
        max_tokens: Maximum tokens to generate
        stream: If True, returns a generator yielding text chunks.
                If False, returns the complete response string.

    Returns:
        str if stream=False, Generator[str] if stream=True
    """
    if stream:
        return _generate_streaming(
            messages=messages,
            provider=provider,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # --- Non-streaming path ---
    client, model, protocol = get_client(provider)

    if protocol == "openai-compatible":
        api_messages = list(messages)
        if system:
            api_messages = [{"role": "system", "content": system}] + api_messages

        response = client.chat.completions.create(
            model=model,
            messages=api_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        return response.choices[0].message.content

    elif protocol == "anthropic":
        api_messages = _convert_messages_for_claude(messages)
        kwargs = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)
        return response.content[0].text


def generate_with_metadata(
    messages,
    provider="kimi",
    system=None,
    temperature=1.0,
    max_tokens=4096,
) -> Dict[str, Any]:
    """
    Generate with full metadata including actual token usage from API.
    Use this for benchmarking and cost tracking.

    Returns:
        {
            "text": str,           # The generated response text
            "usage": {             # Actual token usage from API
                "prompt_tokens": int,
                "completion_tokens": int,
                "total_tokens": int
            },
            "model": str,          # Model name used
            "provider": str        # Provider name
        }
    """
    client, model, protocol = get_client(provider)
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if protocol == "openai-compatible":
        api_messages = list(messages)
        if system:
            api_messages = [{"role": "system", "content": system}] + api_messages

        response = client.chat.completions.create(
            model=model,
            messages=api_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        text = response.choices[0].message.content

        # Extract actual usage metadata
        if hasattr(response, 'usage') and response.usage:
            usage = {
                "prompt_tokens": getattr(response.usage, 'prompt_tokens', 0),
                "completion_tokens": getattr(response.usage, 'completion_tokens', 0),
                "total_tokens": getattr(response.usage, 'total_tokens', 0)
            }

    elif protocol == "anthropic":
        api_messages = _convert_messages_for_claude(messages)
        kwargs = {
            "model": model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)
        text = response.content[0].text

        # Extract actual usage metadata
        if hasattr(response, 'usage') and response.usage:
            usage = {
                "prompt_tokens": getattr(response.usage, 'input_tokens', 0),
                "completion_tokens": getattr(response.usage, 'output_tokens', 0),
                "total_tokens": getattr(response.usage, 'input_tokens', 0) + getattr(response.usage, 'output_tokens', 0)
            }

    return {
        "text": text,
        "usage": usage,
        "model": model,
        "provider": provider
    }


def select_provider(task_type: str = "default", benchmark: bool = False) -> str:
    """
    Metadata-based provider selection.

    Args:
        task_type: 'default', 'reasoning', 'cost_sensitive', 'fast'
        benchmark: If True, force OpenAI for consistent benchmarking

    Returns:
        Provider name string
    """
    if benchmark:
        return "openai"

    if task_type == "reasoning":
        return "claude"  # Claude excels at complex reasoning
    elif task_type == "cost_sensitive":
        return "kimi"    # 5x+ cheaper than frontier models
    elif task_type == "fast":
        return "openai"  # OpenAI fastest for production
    else:
        return "openai"  # Default: OpenAI for speed/reliability


# --- Convenience wrappers for common patterns ---

def analyze(
    prompt: str,
    provider: str = None,
    system: str = "You are a payments dispute analysis expert.",
    **kwargs
) -> str:
    """Non-streaming analysis with default system prompt."""
    if provider is None:
        provider = select_provider()
    return generate(
        messages=[{"role": "user", "content": prompt}],
        provider=provider,
        system=system,
        stream=False,
        **kwargs
    )


def analyze_stream(
    prompt: str,
    provider: str = None,
    system: str = "You are a payments dispute analysis expert.",
    **kwargs
) -> Generator[str, None, None]:
    """Streaming analysis with default system prompt."""
    if provider is None:
        provider = select_provider()
    return generate(
        messages=[{"role": "user", "content": prompt}],
        provider=provider,
        system=system,
        stream=True,
        **kwargs
    )