from langfuse import get_client
from langfuse.api import UnauthorizedError
from langfuse.langchain import CallbackHandler
import logging

logger = logging.getLogger(__name__)

def get_langfuse_handler():
    # Initialize Langfuse client
    langfuse = get_client()
    try:
        # Verify connection
        if langfuse.auth_check():
            logger.info("Langfuse client is authenticated and ready!")
        else:
            logger.error("Authentication failed. Please check your credentials and host.")
        # Initialize Langfuse CallbackHandler for LangChain (tracing)
    except UnauthorizedError as e:
        logger.error("Authentication failed. Please check your credentials and host.")
    langfuse_handler = CallbackHandler()
    return langfuse_handler