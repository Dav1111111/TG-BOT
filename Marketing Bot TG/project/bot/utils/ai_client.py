"""
Module for OpenAI client functions
"""
import logging
import httpx
from openai import AsyncOpenAI
from bot.config import config

logger = logging.getLogger(__name__)

def get_ai_client():
    """Initialize and return an OpenAI client"""
    try:
        client = AsyncOpenAI(
            api_key=config.OPENAI_API_KEY,
            http_client=httpx.AsyncClient()
        )
        return client
    except Exception as e:
        logger.error(f"Error initializing OpenAI client: {e}")
        raise

async def generate_gpt_response(messages, model=None, max_tokens=None, temperature=None):
    """
    Generate a response from the GPT model

    Args:
        messages (list): List of message dictionaries with 'role' and 'content'
        model (str, optional): The model to use. Defaults to config.GPT_MODEL.
        max_tokens (int, optional): Maximum tokens to generate. Defaults to config.GPT_MAX_TOKENS.
        temperature (float, optional): Sampling temperature. Defaults to config.GPT_TEMP.

    Returns:
        str: The generated response text
    """
    client = get_ai_client()
    model = model or config.GPT_MODEL
    max_tokens = max_tokens or config.GPT_MAX_TOKENS
    temperature = temperature or config.GPT_TEMP

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error generating GPT response: {e}")
        raise
