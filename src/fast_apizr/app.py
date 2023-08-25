import logging

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from generator.analyzr import Analyzr
from generator.configuration import Configuration
from generator.fastApiAppGenerator import FastApiAppGenerator
from generator.errorLogger import LogError

logger.info("Initializing the FastAPI app for Fast APIzr")
app = FastAPI()


@app.post("/get_fastapi_code/")
async def create_file(conf: Configuration, analyse: Analyzr):
    """Generate FastAPI code based on the provided configuration and analysis.

    Args:
        conf (Configuration): The configuration details for the FastAPI code generation.
        analyse (Analyzr): The analysis details to guide the code generation.

    Returns:
        PlainTextResponse: The generated FastAPI code.
    """
    try:
        logger.debug("Attempting to generate FastAPI code")
        result: str = FastApiAppGenerator(conf, analyse).gen_fastapi_app()
    except Exception as e:
        logger.error(f"Error during FastAPI code generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    return PlainTextResponse(content=result, status_code=200)
