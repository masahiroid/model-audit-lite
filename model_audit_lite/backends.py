"""Model-loading and text generation, isolated from the CLI and the probe
engine. A backend turns (repo_id, decoding settings) into a `GenerateFn`:

    generate(user_prompt, assistant_prefill="") -> response_text

`assistant_prefill` seeds the assistant turn: the model continues from that
text instead of starting its own reply. An empty prefill is an ordinary turn.
The returned text is only what the model generated (the prefill is not echoed),
so judging looks at what the model itself produced.
"""
from __future__ import annotations

import os
from typing import Callable

from .constants import TRUST_REMOTE_CODE_ENABLED_VALUE, TRUST_REMOTE_CODE_ENV_VAR

GenerateFn = Callable[..., str]


def _thinking_kwargs(thinking: str) -> dict:
    # thinking: "default" (template default) | "on" | "off"
    return {} if thinking == "default" else {"enable_thinking": thinking == "on"}


def _templated_input(tokenizer, user_prompt: str, assistant_prefill: str, thinking: str, **extra):
    """Render the chat template to model-ready input. With a prefill, the last
    message is the (partial) assistant turn and `continue_final_message` makes
    the model keep writing it; without one, a normal generation prompt."""
    kwargs = {**_thinking_kwargs(thinking), **extra}
    if assistant_prefill:
        messages = [{"role": "user", "content": user_prompt}, {"role": "assistant", "content": assistant_prefill}]
        return tokenizer.apply_chat_template(messages, add_generation_prompt=False, continue_final_message=True, **kwargs)
    messages = [{"role": "user", "content": user_prompt}]
    return tokenizer.apply_chat_template(messages, add_generation_prompt=True, **kwargs)


def _trust_remote_code_enabled() -> bool:
    # Opt-in only: some tokenizers (e.g. llm-jp) ship custom code needed to load.
    return os.environ.get(TRUST_REMOTE_CODE_ENV_VAR) == TRUST_REMOTE_CODE_ENABLED_VALUE


def load_backend(backend: str, repo_id: str, max_tokens: int, thinking: str = "default") -> GenerateFn:
    if backend == "mlx-lm":
        return _load_mlx(repo_id, max_tokens, thinking)
    if backend == "transformers":
        return _load_transformers(repo_id, max_tokens, thinking)
    raise ValueError(
        f"Unknown backend: {backend}. Use 'mlx-lm' or 'transformers', "
        "or call the Python API with your own generate function."
    )


def _load_mlx(repo_id: str, max_tokens: int, thinking: str) -> GenerateFn:
    from mlx_lm import generate, load

    tokenizer_config = {"trust_remote_code": True} if _trust_remote_code_enabled() else {}
    model, tokenizer = load(repo_id, tokenizer_config=tokenizer_config)

    def generate_fn(user_prompt: str, assistant_prefill: str = "") -> str:
        prompt = _templated_input(tokenizer, user_prompt, assistant_prefill, thinking)
        return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False)

    return generate_fn


def _load_transformers(repo_id: str, max_tokens: int, thinking: str) -> GenerateFn:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    trust = _trust_remote_code_enabled()
    tokenizer = AutoTokenizer.from_pretrained(repo_id, trust_remote_code=trust)
    model = AutoModelForCausalLM.from_pretrained(repo_id, trust_remote_code=trust).eval()

    def generate_fn(user_prompt: str, assistant_prefill: str = "") -> str:
        inputs = _templated_input(
            tokenizer, user_prompt, assistant_prefill, thinking, return_tensors="pt"
        )
        with torch.no_grad():
            out = model.generate(inputs, max_new_tokens=max_tokens, do_sample=False)
        return tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True)

    return generate_fn


def free_model_memory() -> None:
    """Release a backend's model before loading the next (they must not be
    resident together on a 16GB machine)."""
    import gc

    gc.collect()
    try:
        import mlx.core as mx

        mx.clear_cache()
    except Exception:
        pass
    try:
        import torch

        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except Exception:
        pass
