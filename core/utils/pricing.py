"""
pricing.py — Dynamic LLM cost calculator for Blackbox AI models.

Prices are in USD per 1,000,000 tokens (as listed in pricing.md).
Model IDs may be Blackbox-namespaced (e.g. "blackboxai/google/gemini-3-pro-preview")
or bare (e.g. "google/gemini-3-pro-preview"). Both are handled.
"""

from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Pricing table  –  (input_cost_per_1M, output_cost_per_1M) in USD
# Source: pricing.md from Blackbox AI documentation
# ---------------------------------------------------------------------------
PRICING: dict[str, Tuple[float, float]] = {
    # Anthropic
    "anthropic/claude-sonnet-4.6":                      (3.00,  15.00),
    "anthropic/claude-opus-4.6":                        (5.00,  25.00),
    "anthropic/claude-opus-4.7":                        (5.00,  25.00),
    "anthropic/claude-sonnet-4.5":                      (3.00,  15.00),
    "anthropic/claude-opus-4.5":                        (5.00,  25.00),
    "anthropic/claude-3-haiku":                         (0.25,   1.25),
    "anthropic/claude-3-haiku:beta":                    (0.25,   1.25),
    "anthropic/claude-3-opus":                          (15.00, 75.00),
    "anthropic/claude-3-opus:beta":                     (15.00, 75.00),
    "anthropic/claude-3-sonnet":                        (3.00,  15.00),
    "anthropic/claude-3-sonnet:beta":                   (3.00,  15.00),
    "anthropic/claude-3.5-haiku":                       (0.80,   4.00),
    "anthropic/claude-3.5-haiku-20241022":              (0.80,   4.00),
    "anthropic/claude-3.5-haiku-20241022:beta":         (0.80,   4.00),
    "anthropic/claude-3.5-haiku:beta":                  (0.80,   4.00),
    "anthropic/claude-3.5-sonnet":                      (3.00,  15.00),
    "anthropic/claude-3.5-sonnet-20240620":             (3.00,  15.00),
    "anthropic/claude-3.5-sonnet-20240620:beta":        (3.00,  15.00),
    "anthropic/claude-3.5-sonnet:beta":                 (3.00,  15.00),
    "anthropic/claude-3.7-sonnet":                      (3.00,  15.00),
    "anthropic/claude-3.7-sonnet:beta":                 (3.00,  15.00),
    "anthropic/claude-3.7-sonnet:thinking":             (3.00,  15.00),
    "anthropic/claude-opus-4":                          (15.00, 75.00),
    "anthropic/claude-sonnet-4":                        (3.00,  15.00),
    "anthropic/claude-2":                               (8.00,  24.00),
    "anthropic/claude-2:beta":                          (8.00,  24.00),
    "anthropic/claude-2.0":                             (8.00,  24.00),
    "anthropic/claude-2.0:beta":                        (8.00,  24.00),
    "anthropic/claude-2.1":                             (8.00,  24.00),
    "anthropic/claude-2.1:beta":                        (8.00,  24.00),

    # OpenAI
    "openai/gpt-5.2-codex":                            (1.75,  14.00),
    "openai/gpt-5.2":                                  (1.75,  14.00),
    "openai/chatgpt-4o-latest":                        (5.00,  15.00),
    "openai/codex-mini":                               (1.50,   6.00),
    "openai/gpt-3.5-turbo-0613":                       (1.00,   2.00),
    "openai/gpt-3.5-turbo-16k":                        (3.00,   4.00),
    "openai/gpt-3.5-turbo-instruct":                   (1.50,   2.00),
    "openai/gpt-4":                                    (30.00, 60.00),
    "openai/gpt-4-0314":                               (30.00, 60.00),
    "openai/gpt-4-turbo":                              (10.00, 30.00),
    "openai/gpt-4-1106-preview":                       (10.00, 30.00),
    "openai/gpt-4-turbo-preview":                      (10.00, 30.00),
    "openai/gpt-4.1":                                  (2.00,   8.00),
    "openai/gpt-4.1-mini":                             (0.40,   1.60),
    "openai/gpt-4.1-nano":                             (0.10,   0.40),
    "openai/gpt-4.5-preview":                          (75.00, 150.00),
    "openai/gpt-4o":                                   (2.50,  10.00),
    "openai/gpt-4o-2024-05-13":                        (5.00,  15.00),
    "openai/gpt-4o-2024-08-06":                        (2.50,  10.00),
    "openai/gpt-4o-2024-11-20":                        (2.50,  10.00),
    "openai/gpt-4o:extended":                          (6.00,  18.00),
    "openai/gpt-4o-search-preview":                    (2.50,  10.00),
    "openai/gpt-4o-mini":                              (0.15,   0.60),
    "openai/gpt-4o-mini-2024-07-18":                   (0.15,   0.60),
    "openai/gpt-4o-mini-search-preview":               (0.15,   0.60),
    "openai/gpt-5.1":                                  (1.25,  10.00),
    "openai/gpt-5.1-codex":                            (1.25,  10.00),
    "openai/gpt-5.4":                                  (2.50,  15.00),
    "openai/gpt-5.4-pro":                              (30.00, 180.00),
    "openai/gpt-5.5":                                  (5.00,  20.00),
    "openai/o1":                                       (15.00, 60.00),
    "openai/o1-mini":                                  (1.10,   4.40),
    "openai/o1-mini-2024-09-12":                       (1.10,   4.40),
    "openai/o1-preview":                               (15.00, 60.00),
    "openai/o1-preview-2024-09-12":                    (15.00, 60.00),
    "openai/o1-pro":                                   (150.00,600.00),
    "openai/o3":                                       (2.00,   8.00),
    "openai/o3-mini":                                  (1.10,   4.40),
    "openai/o3-mini-high":                             (1.10,   4.40),
    "openai/o3-pro":                                   (20.00, 80.00),
    "openai/o4-mini":                                  (1.10,   4.40),
    "openai/o4-mini-high":                             (1.10,   4.40),

    # Google
    "google/gemini-3-pro-preview":                     (2.00,  12.00),
    "google/gemini-3.1-pro-preview":                   (2.00,  12.00),
    "google/gemini-flash-1.5":                         (0.07,   0.30),
    "google/gemini-flash-1.5-8b":                      (0.04,   0.15),
    "google/gemini-pro-1.5":                           (1.25,   5.00),
    "google/gemini-2.0-flash-001":                     (0.10,   0.40),
    "google/gemini-2.0-flash-exp:free":                (0.00,   0.00),
    "google/gemini-2.0-flash-lite-001":                (0.07,   0.30),
    "google/gemini-2.5-flash":                         (0.30,   2.50),
    "google/gemini-2.5-flash-lite-preview-06-17":      (0.10,   0.40),
    "google/gemini-2.5-flash-preview":                 (0.15,   0.60),
    "google/gemini-2.5-flash-preview:thinking":        (0.15,   3.50),
    "google/gemini-2.5-flash-preview-05-20":           (0.15,   0.60),
    "google/gemini-2.5-flash-preview-05-20:thinking":  (0.15,   3.50),
    "google/gemini-2.5-pro":                           (1.25,  10.00),
    "google/gemini-2.5-pro-exp-03-25":                 (0.00,   0.00),
    "google/gemini-2.5-pro-preview-05-06":             (1.25,  10.00),
    "google/gemini-2.5-pro-preview":                   (1.25,  10.00),
    "google/gemma-2-27b-it":                           (0.80,   0.80),
    "google/gemma-2-9b-it":                            (0.20,   0.20),
    "google/gemma-2-9b-it:free":                       (0.00,   0.00),
    "google/gemma-3-12b-it":                           (0.05,   0.10),
    "google/gemma-3-12b-it:free":                      (0.00,   0.00),
    "google/gemma-3-27b-it":                           (0.09,   0.17),
    "google/gemma-3-27b-it:free":                      (0.00,   0.00),
    "google/gemma-3-4b-it":                            (0.02,   0.04),
    "google/gemma-3-4b-it:free":                       (0.00,   0.00),
    "google/gemma-3n-e4b-it":                          (0.02,   0.04),
    "google/gemma-3n-e4b-it:free":                     (0.00,   0.00),

    # MiniMax
    "minimax/minimax-m1":                              (0.30,   1.65),
    "minimax/minimax-m2":                              (0.26,   1.02),
    "minimax/minimax-m2.5":                            (0.30,   1.20),
    "minimax/minimax-m2.7":                            (0.30,   1.20),
    "minimax/minimax-01":                              (0.20,   1.10),

    # Meta Llama
    "meta-llama/llama-3-70b-instruct":                 (0.30,   0.40),
    "meta-llama/llama-3-8b-instruct":                  (0.03,   0.06),
    "meta-llama/llama-3.1-405b":                       (2.00,   2.00),
    "meta-llama/llama-3.1-405b-instruct":              (0.80,   0.80),
    "meta-llama/llama-3.1-70b-instruct":               (0.10,   0.28),
    "meta-llama/llama-3.1-8b-instruct":                (0.02,   0.02),
    "meta-llama/llama-3.2-11b-vision-instruct":        (0.05,   0.05),
    "meta-llama/llama-3.2-11b-vision-instruct:free":   (0.00,   0.00),
    "meta-llama/llama-3.2-1b-instruct":                (0.01,   0.01),
    "meta-llama/llama-3.2-3b-instruct":                (0.00,   0.01),
    "meta-llama/llama-3.2-90b-vision-instruct":        (1.20,   1.20),
    "meta-llama/llama-3.3-70b-instruct":               (0.04,   0.12),
    "meta-llama/llama-3.3-70b-instruct:free":          (0.00,   0.00),
    "meta-llama/llama-4-maverick":                     (0.15,   0.60),
    "meta-llama/llama-4-maverick:free":                (0.00,   0.00),
    "meta-llama/llama-4-scout":                        (0.08,   0.30),
    "meta-llama/llama-4-scout:free":                   (0.00,   0.00),

    # DeepSeek
    "deepseek/deepseek-chat":                          (0.38,   0.89),
    "deepseek/deepseek-chat:free":                     (0.00,   0.00),
    "deepseek/deepseek-chat-v3-0324":                  (0.28,   0.88),
    "deepseek/deepseek-chat-v3-0324:free":             (0.00,   0.00),
    "deepseek/deepseek-r1":                            (0.45,   2.15),
    "deepseek/deepseek-r1:free":                       (0.00,   0.00),
    "deepseek/deepseek-r1-0528":                       (0.50,   2.15),
    "deepseek/deepseek-r1-0528:free":                  (0.00,   0.00),
    "deepseek/deepseek-r1-distill-llama-70b":          (0.10,   0.40),
    "deepseek/deepseek-r1-distill-llama-8b":           (0.04,   0.04),
    "deepseek/deepseek-prover-v2":                     (0.50,   2.18),

    # Qwen
    "qwen/qwen-2.5-72b-instruct":                     (0.12,   0.39),
    "qwen/qwen-2.5-72b-instruct:free":                 (0.00,   0.00),
    "qwen/qwen-2.5-7b-instruct":                       (0.04,   0.10),
    "qwen/qwen-2.5-coder-32b-instruct":                (0.06,   0.15),
    "qwen/qwq-32b":                                    (0.07,   0.15),
    "qwen/qwq-32b:free":                               (0.00,   0.00),
    "qwen/qwen3-235b-a22b":                            (0.13,   0.60),
    "qwen/qwen3-235b-a22b:free":                       (0.00,   0.00),
    "qwen/qwen3-32b":                                  (0.10,   0.30),
    "qwen/qwen3-32b:free":                             (0.00,   0.00),
    "qwen/qwen3-14b":                                  (0.06,   0.24),
    "qwen/qwen3-8b":                                   (0.04,   0.14),

    # Mistral
    "mistralai/mistral-large":                         (2.00,   6.00),
    "mistralai/mistral-large-2407":                    (2.00,   6.00),
    "mistralai/mistral-large-2411":                    (2.00,   6.00),
    "mistralai/mixtral-8x22b-instruct":                (0.90,   0.90),
    "mistralai/mixtral-8x7b-instruct":                 (0.08,   0.24),
    "mistralai/mistral-7b-instruct":                   (0.03,   0.05),
    "mistralai/mistral-7b-instruct:free":              (0.00,   0.00),
    "mistralai/mistral-medium-3":                      (0.40,   2.00),
    "mistralai/codestral-2501":                        (0.30,   0.90),
    "mistralai/magistral-medium-2506":                 (2.00,   5.00),
    "mistralai/magistral-small-2506":                  (0.50,   1.50),

    # xAI
    "x-ai/grok-3":                                     (3.00,  15.00),
    "x-ai/grok-3-beta":                                (3.00,  15.00),
    "x-ai/grok-3-mini":                                (0.30,   0.50),
    "x-ai/grok-3-mini-beta":                           (0.30,   0.50),
    "x-ai/grok-2-1212":                                (2.00,  10.00),
    "x-ai/grok-vision-beta":                           (5.00,  15.00),
    "x-ai/grok-code-fast-1:free":                      (0.00,   0.00),

    # Amazon
    "amazon/nova-lite-v1":                             (0.06,   0.24),
    "amazon/nova-micro-v1":                            (0.04,   0.14),
    "amazon/nova-pro-v1":                              (0.80,   3.20),

    # Cohere
    "cohere/command":                                  (1.00,   2.00),
    "cohere/command-a":                                (2.50,  10.00),
    "cohere/command-r":                                (0.50,   1.50),
    "cohere/command-r-plus":                           (3.00,  15.00),

    # Microsoft
    "microsoft/phi-4":                                 (0.07,   0.14),
    "microsoft/phi-4-multimodal-instruct":             (0.05,   0.10),
    "microsoft/phi-4-reasoning-plus":                  (0.07,   0.35),
    "microsoft/wizardlm-2-8x22b":                      (0.48,   0.48),

    # NVIDIA
    "nvidia/llama-3.1-nemotron-70b-instruct":          (0.12,   0.30),
    "nvidia/llama-3.1-nemotron-ultra-253b-v1":         (0.60,   1.80),

    # Perplexity
    "perplexity/sonar":                                (1.00,   1.00),
    "perplexity/sonar-pro":                            (3.00,  15.00),
    "perplexity/r1-1776":                              (2.00,   8.00),

    # Blackbox
    "blackbox-search":                                 (0.20,   0.50),
}

# ---------------------------------------------------------------------------
# Aliases: Blackbox-namespaced → canonical pricing key
# Pattern: "blackboxai/<provider>/<model>" → "<provider>/<model>"
# ---------------------------------------------------------------------------
def _normalize_model_id(model_id: str) -> str:
    """
    Strip the 'blackboxai/' prefix used by Blackbox API calls so the ID
    matches the keys in the PRICING table, and prepend 'google/' for bare
    Gemini/Gemma model names.

    Examples:
        "blackboxai/google/gemini-3-pro-preview"  → "google/gemini-3-pro-preview"
        "gemini-2.5-flash"                        → "google/gemini-2.5-flash"
        "google/gemini-2.0-flash-001"             → "google/gemini-2.0-flash-001"
    """
    prefix = "blackboxai/"
    if model_id.startswith(prefix):
        model_id = model_id[len(prefix):]
    
    # Prepend 'google/' prefix for bare Gemini and Gemma model names
    if (model_id.startswith("gemini-") or model_id.startswith("gemma-")) and not model_id.startswith("google/"):
        model_id = "google/" + model_id
        
    return model_id


def get_price(model_id: str) -> Tuple[float, float]:
    """
    Return (input_cost_per_1M, output_cost_per_1M) in USD for the given model.
    Falls back to (0.0, 0.0) if the model is not found.
    """
    canonical = _normalize_model_id(model_id).lower()
    return PRICING.get(canonical, (0.0, 0.0))


def calculate_cost(
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """
    Calculate the total cost in USD for a single LLM call.

    Args:
        model_id:          Raw model ID (with or without 'blackboxai/' prefix).
        prompt_tokens:     Number of input/prompt tokens consumed.
        completion_tokens: Number of output/completion tokens produced.

    Returns:
        Total cost in USD (float, rounded to 8 decimal places).
    """
    input_rate, output_rate = get_price(model_id)
    cost = (prompt_tokens / 1_000_000) * input_rate + \
           (completion_tokens / 1_000_000) * output_rate
    return round(cost, 8)


def get_model_pricing_info(model_id: str) -> dict:
    """
    Return a human-readable pricing summary for a model.
    """
    canonical = _normalize_model_id(model_id)
    input_rate, output_rate = get_price(model_id)
    return {
        "model_id":             model_id,
        "canonical_id":         canonical,
        "input_cost_per_1M":    input_rate,
        "output_cost_per_1M":   output_rate,
        "in_pricing_table":     canonical.lower() in PRICING,
    }
