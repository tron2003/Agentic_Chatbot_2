import sys
import os
import yaml
import logging
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama

from agentic_chatbot.exception.exception import LLMException
from agentic_chatbot.logging.logging_utils import get_correlation_id

logger = logging.getLogger(__name__)

load_dotenv()


class LLMLoader:
    """Loads and configures LLM instances based on config."""

    def __init__(self):
        correlation_id = get_correlation_id()
        try:
            logger.debug(
                "Loading LLM configuration", extra={"correlation_id": correlation_id}
            )

            with open("config/config.yaml", "r") as file:
                self.config = yaml.safe_load(file)

            logger.debug(
                "LLM configuration loaded successfully",
                extra={"correlation_id": correlation_id},
            )
        except FileNotFoundError as e:
            logger.error(
                "Config file not found",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise LLMException(
                "Failed to load config/config.yaml", sys, correlation_id=correlation_id
            )
        except yaml.YAMLError as e:
            logger.error(
                "Failed to parse YAML config",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise LLMException(
                f"Invalid YAML in config file: {str(e)}",
                sys,
                correlation_id=correlation_id,
            )
        except Exception as e:
            logger.error(
                "Unexpected error loading config",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise LLMException(
                f"Failed to initialize LLMLoader: {str(e)}",
                sys,
                correlation_id=correlation_id,
            )

    def load_llm(self):
        """Load and instantiate LLM based on active provider."""
        correlation_id = get_correlation_id()

        try:
            provider = self.config["llm"]["active_provider"]
            logger.debug(
                f"Loading LLM provider: {provider}",
                extra={"correlation_id": correlation_id},
            )

            if provider == "local":
                llm_config = self.config["llm"]["local"]
                logger.info(
                    "Initializing local OpenAI-compatible LLM",
                    extra={"correlation_id": correlation_id, "provider": "local"},
                )

                return ChatOpenAI(
                    model=llm_config["model_name"],
                    api_key=llm_config["api_key"],
                    base_url=llm_config["base_url"],
                )

            elif provider == "local2":
                llm_config = self.config["llm"]["local2"]
                logger.info(
                    "Initializing Ollama LLM",
                    extra={"correlation_id": correlation_id, "provider": "local2"},
                )

                return ChatOllama(
                    model=llm_config["model_name"],
                    base_url=llm_config["base_url"],
                    temperature=llm_config.get("temperature", 0.5),
                )

            elif provider == "claude":
                llm_config = self.config["llm"]["claude"]
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    logger.error(
                        "ANTHROPIC_API_KEY not set in environment",
                        extra={"correlation_id": correlation_id},
                    )
                    raise LLMException(
                        "ANTHROPIC_API_KEY environment variable not set",
                        sys,
                        correlation_id=correlation_id,
                    )

                logger.info(
                    "Initializing Claude LLM",
                    extra={"correlation_id": correlation_id, "provider": "claude"},
                )

                return ChatAnthropic(
                    model=llm_config["model_name"],
                    api_key=api_key,
                    temperature=llm_config["temperature"],
                )

            elif provider == "openrouter":
                llm_config = self.config["llm"]["openrouter"]
                api_key = os.getenv("OPENROUTER_API_KEY")
                if not api_key:
                    logger.error(
                        "OPENROUTER_API_KEY not set in environment",
                        extra={"correlation_id": correlation_id},
                    )
                    raise LLMException(
                        "OPENROUTER_API_KEY environment variable not set",
                        sys,
                        correlation_id=correlation_id,
                    )

                logger.info(
                    "Initializing OpenRouter LLM",
                    extra={"correlation_id": correlation_id, "provider": "openrouter"},
                )

                return ChatOpenAI(
                    model=llm_config["model_name"],
                    api_key=api_key,
                    base_url=llm_config["base_url"],
                    temperature=llm_config.get("temperature", 0.5),
                )

            else:
                logger.error(
                    f"Unknown LLM provider: {provider}",
                    extra={"correlation_id": correlation_id},
                )
                raise LLMException(
                    f"Unknown LLM provider: {provider}",
                    sys,
                    correlation_id=correlation_id,
                    error_code="UNKNOWN_PROVIDER",
                )

        except LLMException:
            raise
        except KeyError as e:
            logger.error(
                f"Missing required config key: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise LLMException(
                f"Invalid LLM configuration: {str(e)}",
                sys,
                correlation_id=correlation_id,
            )
        except Exception as e:
            logger.error(
                f"Failed to load LLM: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise LLMException(
                f"Failed to load LLM: {str(e)}", sys, correlation_id=correlation_id
            )
